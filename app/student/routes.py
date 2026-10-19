# app/student/routes.py
import io
import os
from collections import defaultdict
import json
import base64
from functools import lru_cache
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
                # LearningRecord.staff_id は users.id を参照するため current_user.id を使用
                new_record = LearningRecord(
                    student_id=new_student.id,
                    staff_id=current_user.id,
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


@student_bp.route("/reorder", methods=["POST"])
@login_required
@roles_required("admin", "staff")
def reorder_students():
    """生徒の並び順（表示順）を一括更新してDBに保存するAPI"""
    data = request.get_json() or {}
    order_ids = data.get("order")
    if not order_ids or not isinstance(order_ids, list):
        return jsonify({"status": "error", "message": "order list is required"}), 400

    for index, student_id in enumerate(order_ids, start=1):
        try:
            sid = int(student_id)
            student = Student.query.get(sid)
            if student:
                student.display_order = index
        except (ValueError, TypeError):
            continue

    db.session.commit()
    return jsonify({"status": "success", "message": "順番をDBに保存しました"})


def get_sunday_of_week(d: date) -> date:
    """
    指定された日付の週の日曜日（毎週日曜日のレッスン日）を取得する。
    Pythonの weekday(): 月=0, 火=1, ..., 土=5, 日=6。
    - 日曜日の場合はそのまま
    - 月〜土の場合はその週の日曜日（(6 - d.weekday())日後）
    """
    days_to_add = 6 - d.weekday()
    return d + timedelta(days=days_to_add)


def get_attendance_dates(target_date, count=4):
    """
    target_date（毎週日曜日）を最新として、直近の日曜レッスン日を合計 count 日分（昇順）取得する。
    DBに過去の日曜日の学習記録があればその日付を採用し、
    足りない場合は過去に遡って 7 日刻み（毎週日曜日）で補完する。
    """
    target_date = get_sunday_of_week(target_date)

    distinct_dates = (
        db.session.query(LearningRecord.lesson_date)
        .filter(LearningRecord.lesson_date <= target_date)
        .distinct()
        .order_by(LearningRecord.lesson_date.desc())
        .limit(count * 2)
        .all()
    )
    # 日曜日（weekday == 6）の日付のみを抽出
    found_dates = [d[0] for d in distinct_dates if d[0].weekday() == 6][:count]

    if not found_dates or target_date not in found_dates:
        found_dates.insert(0, target_date)
        found_dates = found_dates[:count]

    needed = count - len(found_dates)
    oldest = found_dates[-1] if found_dates else target_date
    for i in range(1, needed + 1):
        found_dates.append(oldest - timedelta(days=7 * i))

    found_dates.sort()
    return found_dates


def get_fiscal_year(target_date):
    """年度（4月〜翌年3月）を計算"""
    return target_date.year if target_date.month >= 4 else target_date.year - 1


def get_attendance_matrix(student_ids, dates):
    """
    各生徒・各日付の担当スタッフ名マップと、各日付の出席者数カウントを返す
    """
    records = (
        LearningRecord.query.options(
            joinedload(LearningRecord.writer_staff).joinedload(User.staff_profile)
        )
        .filter(
            LearningRecord.student_id.in_(student_ids),
            LearningRecord.lesson_date.in_(dates),
        )
        .all()
    )

    student_attendance = defaultdict(dict)
    attendance_counts = {d: 0 for d in dates}

    for rec in records:
        staff_name = "─"
        if rec.writer_staff:
            if (
                rec.writer_staff.staff_profile
                and rec.writer_staff.staff_profile.last_name_kanji
            ):
                staff_name = rec.writer_staff.staff_profile.last_name_kanji
            elif rec.writer_staff.name:
                staff_name = rec.writer_staff.name.split()[0]

        student_attendance[rec.student_id][rec.lesson_date] = staff_name
        attendance_counts[rec.lesson_date] = (
            attendance_counts.get(rec.lesson_date, 0) + 1
        )

    return student_attendance, attendance_counts


@student_bp.route("/attendance")
@login_required
def attendance_list():
    # 1. クエリパラメータから日付を取得（毎週日曜日のレッスン日に自動補正）
    date_str = request.args.get("date")
    if date_str:
        try:
            raw_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            target_date = get_sunday_of_week(raw_date)
        except ValueError:
            target_date = get_sunday_of_week(datetime.now().date())
    else:
        target_date = get_sunday_of_week(datetime.now().date())

    dates = get_attendance_dates(target_date, count=4)
    date_columns = [
        {
            "date": d,
            "label": f"{d.month}月{d.day}日",
            "iso": d.strftime("%Y-%m-%d"),
        }
        for d in dates
    ]

    # 2. 対象生徒の選定（国籍別グループは廃止し、フラットな一覧）
    threshold_date = target_date - timedelta(days=60)
    recent_student_ids = {
        r[0]
        for r in db.session.query(LearningRecord.student_id)
        .filter(LearningRecord.lesson_date >= threshold_date)
        .all()
    }
    target_date_student_ids = {
        r[0]
        for r in db.session.query(LearningRecord.student_id)
        .filter(LearningRecord.lesson_date.in_(dates))
        .all()
    }
    priority_student_ids = {
        s.id for s in Student.query.filter_by(is_priority=True).all()
    }
    ordered_student_ids = {
        s.id for s in Student.query.filter(Student.display_order > 0).all()
    }

    target_ids = (
        recent_student_ids
        | target_date_student_ids
        | priority_student_ids
        | ordered_student_ids
    )
    if not target_ids:
        target_ids = {s.id for s in Student.query.all()}

    # DBに保存された display_order の昇順、未設定は後方、ID昇順で取得
    students_query = (
        Student.query.filter(Student.id.in_(target_ids))
        .order_by(Student.display_order.asc().nulls_last(), Student.name_kana.asc())
        .all()
    )

    student_attendance, attendance_counts = get_attendance_matrix(
        [s.id for s in students_query], dates
    )

    for s in students_query:
        s.attendance_by_date = student_attendance.get(s.id, {})
        s.assigned_staff_name = s.attendance_by_date.get(target_date, "─")

    fiscal_year = get_fiscal_year(target_date)

    prev_sunday = target_date - timedelta(days=7)
    next_sunday = target_date + timedelta(days=7)

    return render_template(
        "student/attendence.html",
        target_date=target_date,
        prev_sunday=prev_sunday,
        next_sunday=next_sunday,
        fiscal_year=fiscal_year,
        students=students_query,
        date_columns=date_columns,
        attendance_counts=attendance_counts,
        total_count=len(students_query),
    )


@student_bp.route("/attendance/pdf-preview")
@login_required
def attendance_pdf_preview():
    """PDF出力前の最終確認・並び替え画面を表示する"""

    date_str = request.args.get("date")
    order_str = request.args.get("order", "")

    if date_str:
        try:
            raw_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            target_date = get_sunday_of_week(raw_date)
        except ValueError:
            target_date = get_sunday_of_week(datetime.now().date())
    else:
        target_date = get_sunday_of_week(datetime.now().date())

    dates = get_attendance_dates(target_date, count=4)
    date_columns = [
        {
            "date": d,
            "label": f"{d.month}月{d.day}日",
            "iso": d.strftime("%Y-%m-%d"),
        }
        for d in dates
    ]

    ordered_ids = [int(id) for id in order_str.split(",") if id.isdigit()]

    if ordered_ids:
        students_query = Student.query.filter(Student.id.in_(ordered_ids)).all()
        students_map = {s.id: s for s in students_query}
        students = [students_map[sid] for sid in ordered_ids if sid in students_map]
    else:
        threshold_date = target_date - timedelta(days=60)
        recent_ids = {
            r[0]
            for r in db.session.query(LearningRecord.student_id)
            .filter(LearningRecord.lesson_date >= threshold_date)
            .all()
        }
        target_date_ids = {
            r[0]
            for r in db.session.query(LearningRecord.student_id)
            .filter(LearningRecord.lesson_date.in_(dates))
            .all()
        }
        priority_ids = {s.id for s in Student.query.filter_by(is_priority=True).all()}
        ordered_ids_db = {
            s.id for s in Student.query.filter(Student.display_order > 0).all()
        }
        target_ids = recent_ids | target_date_ids | priority_ids | ordered_ids_db
        if not target_ids:
            target_ids = {s.id for s in Student.query.all()}

        students = (
            Student.query.filter(Student.id.in_(target_ids))
            .order_by(Student.name_kana.asc())
            .all()
        )

    if not students:
        flash("PDFに出力する生徒がいません。", "warning")
        return redirect(url_for("student.attendance_list", date=date_str))

    student_attendance, attendance_counts = get_attendance_matrix(
        [s.id for s in students], dates
    )

    for s in students:
        s.attendance_by_date = student_attendance.get(s.id, {})
        s.assigned_staff_name = s.attendance_by_date.get(target_date, "─")

    fiscal_year = get_fiscal_year(target_date)

    return render_template(
        "student/attendance_pdf_preview.html",
        target_date=target_date,
        fiscal_year=fiscal_year,
        students=students,
        date_columns=date_columns,
        attendance_counts=attendance_counts,
    )


@student_bp.route("/attendance/download-pdf")
@login_required
def download_attendance_pdf():
    date_str = request.args.get("date")
    order_str = request.args.get("order", "")

    if date_str:
        try:
            raw_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            target_date = get_sunday_of_week(raw_date)
        except ValueError:
            target_date = get_sunday_of_week(datetime.now().date())
    else:
        target_date = get_sunday_of_week(datetime.now().date())

    dates = get_attendance_dates(target_date, count=4)
    date_columns = [
        {
            "date": d,
            "label": f"{d.month}月{d.day}日",
            "iso": d.strftime("%Y-%m-%d"),
        }
        for d in dates
    ]

    ordered_ids = [int(id) for id in order_str.split(",") if id.isdigit()]

    # 出力対象の生徒を取得（DBのReorderは行わず、指定された順序でPDFを生成）
    if ordered_ids:
        students_query = Student.query.filter(Student.id.in_(ordered_ids)).all()
        students_map = {s.id: s for s in students_query}
        all_students = [students_map[sid] for sid in ordered_ids if sid in students_map]
    else:
        all_students = Student.query.order_by(Student.name_kana.asc()).all()

    student_attendance, attendance_counts = get_attendance_matrix(
        [s.id for s in all_students], dates
    )

    # Base64画像変換
    for student in all_students:
        student.attendance_by_date = student_attendance.get(student.id, {})
        student.face_photo_base64 = None
        if student.face_photo_path:
            try:
                response = requests.get(student.face_photo_path, timeout=5)
                if response.status_code == 200:
                    b64_data = base64.b64encode(response.content).decode("utf-8")
                    content_type = response.headers.get("Content-Type", "image/jpeg")
                    student.face_photo_base64 = f"data:{content_type};base64,{b64_data}"
            except Exception as e:
                current_app.logger.warning(
                    f"Failed to fetch image for student {student.id} during PDF generation: {e}"
                )

    fiscal_year = get_fiscal_year(target_date)

    rendered_html = render_template(
        "student/attendance_pdf_template.html",
        target_date=target_date,
        fiscal_year=fiscal_year,
        date_columns=date_columns,
        all_students=all_students,
        attendance_counts=attendance_counts,
    )

    pdf_buffer = io.BytesIO()
    font_path = os.path.join(current_app.root_path, "fonts", "ipaexg.ttf")
    if not os.path.exists(font_path):
        font_path = os.path.join(current_app.root_path, "static", "fonts", "ipaexg.ttf")

    def link_callback(uri, rel):
        if "HeiseiKakuGo-W5" in uri or "HeiseiMin-W3" in uri:
            return font_path
        return uri

    html_bytes = io.BytesIO(rendered_html.encode("utf-8"))

    pisa_status = pisa.CreatePDF(
        html_bytes,
        dest=pdf_buffer,
        encoding="utf-8",
        link_callback=link_callback,
    )

    if pisa_status.err:
        return "PDF生成中にエラーが発生しました。", 500

    pdf_buffer.seek(0)
    response = make_response(pdf_buffer.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=attendance_{target_date}.pdf"
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response
