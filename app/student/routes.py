# app/student/routes.py
import io
import os
from collections import defaultdict
import json
import base64
from functools import lru_cache
from urllib3.exceptions import InsecureRequestWarning
from datetime import datetime, timedelta, date, timezone
from xhtml2pdf import pisa
import cloudinary
import cloudinary.uploader
import requests
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    jsonify,
    make_response,
)
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from app import db
from app.models import User, Student, LearningRecord, Staff
from app.decorators import roles_required

student_bp = Blueprint("student", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


@lru_cache(maxsize=None)
def get_region_data():
    """地域データをJSONファイルから読み込み、キャッシュする"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "..", "common", "region_data.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)



@lru_cache(maxsize=None)
def get_mother_language_data():
    """母語データをJSONファイルから読み込み、キャッシュする"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, "..", "common", "mother_language.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def allowed_file(filename):
    """Check if the file extension is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _fill_student_data_from_form(student, form):
    """Helper to map form fields to student object."""
    student.name_kana = form.get("student_name_kana") or form.get("name_kana")
    student.country_of_origin = form.get("country_of_origin")
    student.native_language = form.get("native_language")
    student.other_languages = form.get("other_languages")
    student.occupation = form.get("occupation")
    student.residential_area = form.get("residential_area")
    student.jlpt_level = form.get("jlpt_level")
    student.learning_purpose = form.get("learning_purpose")
    student.life_troubles = form.get("life_troubles")
    student.how_knew_class = form.get("how_knew_class")
    student.how_knew_class_other = form.get("how_knew_class_other")
    return student


def upload_face_photo_to_cloudinary(file):
    """
    顔写真をCloudinaryにアップロードし、URLを返します。
    エラーが発生した場合はNoneとエラーメッセージを返します。
    """
    if not file or file.filename == "":
        return None, "顔写真をアップロードしてください。"
    if not allowed_file(file.filename):
        return None, "許可されていないファイル形式です。"

    try:
        upload_result = cloudinary.uploader.upload(
            file,
            folder="students",
            eager=[
                {
                    "crop": "thumb",
                    "gravity": "face",
                    "zoom": 0.7,
                    "width": 200,
                    "height": 200,
                    "fetch_format": "auto",
                    "quality": "auto",
                }
            ],
        )
        # eager変換が成功した場合のURLを取得
        if (
            upload_result
            and "eager" in upload_result
            and len(upload_result["eager"]) > 0
        ):
            return upload_result["eager"][0].get("secure_url"), None
        return (
            None,
            "Cloudinaryへのアップロードは成功しましたが、変換されたURLが見つかりません。",
        )
    except Exception as e:
        current_app.logger.error(f"Cloudinary upload failed: {e}")
        return None, f"画像アップロード中にエラーが発生しました: {str(e)}"


@student_bp.route("/create", methods=["GET", "POST"])
@login_required
@roles_required("admin", "staff")
def create_student():
    """Register a new student and create an initial learning record."""
    if request.method == "POST":
        # --- 1. 画像ファイルの保存処理 ---
        file = request.files.get("face_photo")
        face_photo_path, error_message = upload_face_photo_to_cloudinary(file)

        if error_message:
            flash(error_message, "danger")
            return render_template(
                "student/create.html",
                staff_list=Staff.query.all(),
                region_data=get_region_data(),
                mother_language_data=get_mother_language_data(),
                google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"),
            )

        try:
            new_student = Student(face_photo_path=face_photo_path)
            _fill_student_data_from_form(new_student, request.form)

            db.session.add(new_student)
            db.session.flush()  # new_student.id を確定させる

            today_content = request.form.get("today_learning_content")
            if today_content:
                # Find the Staff record associated with the User
                staff_record = Staff.query.filter_by(user_id=current_user.id).first()
                if staff_record:
                    new_record = LearningRecord(
                        student_id=new_student.id,
                        staff_id=staff_record.id,
                        today_learning_content=today_content,
                        lesson_date=date.today(),
                    )
                    db.session.add(new_record)

            db.session.commit()
            flash("受講生の新規登録と学習記録の保存が完了しました！", "success")
            return redirect(url_for("student.student_list"))

        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {str(e)}", "danger")
    staff_list = Staff.query.all()

    return render_template(
        "student/create.html",
        staff_list=staff_list,
        region_data=get_region_data(),
        mother_language_data=get_mother_language_data(),
        google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"),
    )


@student_bp.route("/")
@login_required
def student_list():
    """Display the list of active and inactive students."""
    # Calculate threshold for inactive students (60 days)
    threshold_date = (datetime.now(timezone.utc) - timedelta(days=60)).date()

    active_students = []  # 2ヶ月以内に学習録がある生徒
    inactive_students = []  # 最後の学習録から2ヶ月以上経っている生徒

    # N+1問題を解決するために、各受講生の最新の学習日をサブクエリで一括取得
    latest_record_sub = (
        db.session.query(
            LearningRecord.student_id,
            db.func.max(LearningRecord.lesson_date).label("latest_date"),
        )
        .group_by(LearningRecord.student_id)
        .subquery()
    )

    students_with_date = (
        db.session.query(Student, latest_record_sub.c.latest_date)
        .outerjoin(latest_record_sub, Student.id == latest_record_sub.c.student_id)
        .all()
    )

    for student, latest_date in students_with_date:
        student.display_image = student.face_photo_path
        student.latest_log_date = latest_date

        # 優先フラグが立っている生徒は、最終学習日に関わらず常に「継続中」として扱う
        if student.is_priority:
            active_students.append(student)
            continue

        # 優先でない生徒は、従来通り最終学習日で判定
        if latest_date and latest_date >= threshold_date:
            active_students.append(student)
        else:
            inactive_students.append(student)

    return render_template(
        "student/list.html",
        active_students=active_students,
        inactive_students=inactive_students,
    )


@student_bp.route("/<int:id>/toggle-priority", methods=["POST"])
@login_required
@roles_required("admin", "staff")
def toggle_student_priority(id):
    """生徒の優先フラグを切り替えるAPI"""
    student = Student.query.get_or_404(id)
    data = request.get_json()
    is_priority = data.get("is_priority")

    if is_priority is None:
        return jsonify({"status": "error", "message": "is_priority is required"}), 400

    student.is_priority = bool(is_priority)
    db.session.commit()

    return jsonify({"status": "success", "student_id": id, "is_priority": student.is_priority})


# app/student/routes.py 内
@student_bp.route("/<int:id>/update", methods=["GET", "POST"])
def update_student(id):
    """Update existing student information."""
    student = Student.query.get_or_404(id)

    if request.method == "POST":
        _fill_student_data_from_form(student, request.form)

        file = request.files.get("face_photo")
        if file and file.filename:
            face_photo_path, error_message = upload_face_photo_to_cloudinary(file)
            if error_message:
                flash(error_message, "danger")
                return render_template(
                    "student/edit.html",
                    student=student,
                    staff_list=Staff.query.all(),
                    region_data=get_region_data(),
                    mother_language_data=get_mother_language_data(),
                    google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"),
                )
            if face_photo_path:
                student.face_photo_path = face_photo_path

        try:
            db.session.commit()
            flash(f"{student.name_kana} さんの情報を更新しました。", "success")
            return redirect(url_for("student.student_list"))
        except Exception as e:
            db.session.rollback()
            flash(f"更新中にエラーが発生しました: {str(e)}", "danger")
    return render_template(
        "student/edit.html",
        student=student,
        staff_list=Staff.query.all(),
        region_data=get_region_data(),
        mother_language_data=get_mother_language_data(),
        google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"),
    )


@student_bp.route("/attendance")
@login_required
def attendance_list():
    # 1. クエリパラメータから日付を取得（指定がなければ今日の日付）
    date_str = request.args.get("date")
    if date_str:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        target_date = datetime.now().date()

    # 2. その日の学習記録がある生徒と、優先設定されている生徒の両方を取得
    logs = (
        LearningRecord.query.options(
            joinedload(LearningRecord.student), joinedload(LearningRecord.writer_staff)
        )
        .filter_by(lesson_date=target_date)
        .all()
    )
    # 学習記録から生徒IDと担当者名のマップを作成
    attended_students_map = {
        log.student.id: log.writer_staff.name if log.writer_staff else "自習"
        for log in logs
        if log.student
    }

    # 優先設定されている生徒を取得
    priority_students = Student.query.filter_by(is_priority=True).all()
    priority_student_ids = {s.id for s in priority_students}

    # 表示対象となる全生徒IDを結合（重複排除）
    all_student_ids = set(attended_students_map.keys()) | priority_student_ids
    all_students = Student.query.filter(Student.id.in_(all_student_ids)).all()

    # 3. 国籍ごとに生徒をグループ化
    grouped_students = defaultdict(list)
    for student in all_students:
        # その日の担当者名を設定（出席していなければ '─'）
        student.assigned_staff_name = attended_students_map.get(student.id, "─")
        country = student.country_of_origin or "不明"
        grouped_students[country].append(student)

    return render_template(
        "student/attendence.html",
        target_date=target_date,
        grouped_students=dict(grouped_students),  # 扱いやすいように通常の辞書型に変換
        total_count=len(all_students),
    )


@student_bp.route("/attendance/download-pdf")
@login_required
def download_attendance_pdf():
    # 1. フロントエンドから日付と並び順IDを取得
    date_str = request.args.get("date")
    order_str = request.args.get("order", "")
    priority_ids_str = request.args.get("priority_ids", "")

    target_date = (
        datetime.strptime(date_str, "%Y-%m-%d").date()
        if date_str
        else datetime.now().date()
    )

    # 日付カラム用の日付を計算
    two_weeks_ago = target_date - timedelta(days=14)
    one_week_ago = target_date - timedelta(days=7)
    next_week = target_date + timedelta(days=7)

    # 2. 画面で並び替えたIDリストと、DBから取得した優先生徒IDリストを準備
    ordered_ids = [int(id) for id in order_str.split(",") if id.isdigit()]
    priority_ids = {int(id) for id in priority_ids_str.split(",") if id.isdigit()}

    # 3. 優先チェックが入っている生徒をDBから取得
    priority_students_from_db = Student.query.filter_by(is_priority=True).all()
    priority_student_ids_from_db = {s.id for s in priority_students_from_db}

    # 4. 最終的にPDFに表示する生徒のIDリストを作成
    # (優先DB > 画面の並び順)
    final_student_ids = sorted(list(priority_student_ids_from_db), reverse=True)
    for sid in ordered_ids:
        if sid not in priority_student_ids_from_db:
            final_student_ids.append(sid)

    # 5. 該当日の学習記録と生徒情報を取得
    logs = (
        LearningRecord.query.options(joinedload(LearningRecord.student))
        .filter(LearningRecord.lesson_date == target_date)
        .all()
    )
    students_map = {log.student.id: log for log in logs if log.student}

    # --- 過去の出席記録を取得 ---
    student_ids_on_list = final_student_ids
    past_dates = [one_week_ago, two_weeks_ago]
    past_records = (
        LearningRecord.query.options(joinedload(LearningRecord.writer_staff))
        .filter(
            LearningRecord.student_id.in_(student_ids_on_list),
            LearningRecord.lesson_date.in_(past_dates),
        )
        .all()
    )

    # 生徒IDと日付をキーにした担当者マップを作成
    attendance_history = defaultdict(dict)
    for rec in past_records:
        if rec.writer_staff:
            attendance_history[rec.student_id][rec.lesson_date] = rec.writer_staff.name

    # 6. 優先生徒と通常生徒に振り分ける
    priority_students = []
    other_students = []

    # SSL証明書の警告を非表示にする
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

    # 優先生徒と出席生徒の情報を取得
    all_target_students = Student.query.filter(Student.id.in_(final_student_ids)).all()
    all_students_map = {s.id: s for s in all_target_students}

    for student_id in final_student_ids:
        student = all_students_map.get(student_id)
        if not student:
            continue

        # その日の出席情報があれば担当者名を取得、なければ「自習」
        if student_id in students_map:
            log = students_map[student_id]
            staff_user = Staff.query.get(log.staff_id)
            student.assigned_staff_name = (
                staff_user.first_name_kanji if staff_user else "─"
            )

            # 過去の担当者情報を生徒オブジェクトにセット
            student.staff_one_week_ago = attendance_history.get(student.id, {}).get(
                one_week_ago, ""
            )
            student.staff_two_weeks_ago = attendance_history.get(student.id, {}).get(
                two_weeks_ago, ""
            )
        else:
            student.assigned_staff_name = "─"

            # --- 画像をBase64に変換する処理を追加 ---
            student.face_photo_base64 = None  # 属性を初期化しておく
            if student.face_photo_path:
                try:
                    # SSL検証を無効にして画像データを取得
                    response = requests.get(
                        student.face_photo_path, verify=False, timeout=10
                    )
                    if response.status_code == 200:
                        # Base64エンコードして、テンプレートで使えるようにData URI形式にする
                        # ★注意: student.face_photo_path を上書きしない！
                        # データベースのフィールドを汚してしまい、autoflush時にエラーを引き起こす原因になる。
                        # テンプレート専用の新しい属性に格納する。
                        b64_data = base64.b64encode(response.content).decode("utf-8")
                        student.face_photo_base64 = f"data:image/jpeg;base64,{b64_data}"
                except Exception as e:
                    current_app.logger.error(
                        f"Failed to fetch or encode image for student {student.id}: {e}"
                    )

        # 優先生徒は必ず出席者リストへ。それ以外の生徒は出席記録がある場合のみリストに追加。
        if student.is_priority or student_id in students_map:
            priority_students.append(student)
        else:
            other_students.append(student)
    all_students = priority_students + other_students

    # 7. HTMLテンプレートをレンダリング
    rendered_html = render_template(
        "student/attendance_pdf_template.html",
        date_two_weeks_ago=two_weeks_ago.strftime("%m/%d"),
        date_one_week_ago=one_week_ago.strftime("%m/%d"),
        date_target=target_date.strftime("%m/%d"),
        date_next_week=next_week.strftime("%m/%d"),
        all_students=all_students,
        num_priority=len(priority_students),
    )

    # 8. xhtml2pdf を使ってPDFを生成
    pdf_buffer = io.BytesIO()
    font_path = os.path.join(current_app.root_path, "static", "fonts", "ipaexg.ttf")

    # --- 修正: SSL検証を無効化し、日本語フォントを正しく参照させるためのコールバック ---
    import ssl

    # SSL証明書の検証を無効にするグローバルコンテキストを作成
    # これにより、xhtml2pdfが外部URL（例: Cloudinary）から画像を取得する際のSSLエラーを回避します。
    ssl._create_default_https_context = ssl._create_unverified_context

    def link_callback(uri, rel):
        # 日本語フォントファイルへのパスを解決
        if "HeiseiKakuGo-W5" in uri or "HeiseiMin-W3" in uri:
            return font_path
        # それ以外のローカルファイル（CSSなど）へのパスを解決
        # URIが外部リソース（http/https/data）でない場合にのみ、ローカルパスを解決
        return uri

    pisa_status = pisa.CreatePDF(
        io.StringIO(rendered_html),
        dest=pdf_buffer,
        encoding="utf-8",
        link_callback=link_callback,
    )

    if pisa_status.err:
        return "PDF生成中にエラーが発生しました。", 500

    # 9. PDFをレスポンスとして返す
    pdf_buffer.seek(0)
    response = make_response(pdf_buffer.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=attendance_{target_date}.pdf"
    )
    return response
