# app/student/routes.py
import io
import os
from datetime import datetime, timedelta, date, timezone
from collections import defaultdict

import cloudinary
import cloudinary.uploader
import requests
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, make_response
from flask_login import login_required, current_user
from fpdf import FPDF
from PIL import Image
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from app import db
from app.models import User, Student, LearningRecord, Staff
from app.decorators import roles_required

student_bp = Blueprint("student", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

SAITAMA_MUNICIPALITIES = [
    "さいたま市西区", "さいたま市北区", "さいたま市大宮区", "さいたま市見沼区", 
    "さいたま市中央区", "さいたま市桜区", "さいたま市浦和区", "さいたま市南区", 
    "さいたま市緑区", "さいたま市岩槻区",
    "上尾市", "朝霞市", "伊奈町", "入間市", "小鹿野町", "小川町", "桶川市", "越生町",
    "春日部市", "加須市", "神川町", "上里町", "川口市", "川越市", "川島町", "北本市", 
    "行田市", "久喜市", "熊谷市", "鴻巣市", "越谷市", "さいたま市", "坂戸市", "幸手市", 
    "狭山市", "志木市", "白岡市", "杉戸町", "草加市", "祖父江町", "秩父市", "鶴ヶ島市", 
    "ときがわ町", "所沢市", "戸田市", "長瀞町", "滑川町", "新座市", "蓮田市", "鳩山町", 
    "羽生市", "飯能市", "東松山市", "東秩父村", "日高市", "深谷市", "富士見市", 
    "ふじみ野市", "本庄市", "松伏町", "三郷市", "美里町", "皆野町", "宮代町", "三芳町", 
    "毛呂山町", "八潮市", "横瀬町", "吉川市", "吉見町", "寄居町", "和光市"
]


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
                {"crop": "thumb", "gravity": "face", "zoom": 0.7,
                 "width": 200, "height": 200, "fetch_format": "auto", "quality": "auto"}
            ]
        )
        # eager変換が成功した場合のURLを取得
        if upload_result and 'eager' in upload_result and len(upload_result['eager']) > 0:
            return upload_result['eager'][0].get('secure_url'), None
        return None, "Cloudinaryへのアップロードは成功しましたが、変換されたURLが見つかりません。"
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
            return render_template("student/create.html", staff_list=Staff.query.all(), city_list=SAITAMA_MUNICIPALITIES)

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
                        lesson_date=date.today()
                    )
                    db.session.add(new_record)

            db.session.commit()
            flash("受講生の新規登録と学習記録の保存が完了しました！", "success")
            return redirect(url_for("student.student_list"))

        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {str(e)}", "danger")
    staff_list = Staff.query.all()

    return render_template("student/create.html", staff_list=staff_list, city_list=SAITAMA_MUNICIPALITIES)


@student_bp.route("/")
@login_required
def student_list():
    """Display the list of active and inactive students."""
    # Calculate threshold for inactive students (60 days)
    threshold_date = (datetime.now(timezone.utc) - timedelta(days=60)).date()
    
    active_students = []     # 2ヶ月以内に学習録がある生徒
    inactive_students = []   # 最後の学習録から2ヶ月以上経っている生徒
    
    # N+1問題を解決するために、各受講生の最新の学習日をサブクエリで一括取得
    latest_record_sub = db.session.query(
        LearningRecord.student_id,
        db.func.max(LearningRecord.lesson_date).label("latest_date")
    ).group_by(LearningRecord.student_id).subquery()

    students_with_date = db.session.query(Student, latest_record_sub.c.latest_date)\
        .outerjoin(latest_record_sub, Student.id == latest_record_sub.c.student_id)\
        .all()
    
    for student, latest_date in students_with_date:
        student.display_image = student.face_photo_path
        student.latest_log_date = latest_date
        
        if latest_date:
            if latest_date < threshold_date:
                inactive_students.append(student)
            else:
                active_students.append(student)
        else:
            inactive_students.append(student)
            
    return render_template(
        'student/list.html', 
        active_students=active_students, 
        inactive_students=inactive_students
    )


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
                return render_template("student/edit.html", student=student, staff_list=Staff.query.all(), city_list=SAITAMA_MUNICIPALITIES)
            if face_photo_path:
                student.face_photo_path = face_photo_path

        try:
            db.session.commit()
            flash(f"{student.name_kana} さんの情報を更新しました。", "success")
            return redirect(url_for("student.student_list"))
        except Exception as e:
            db.session.rollback()
            flash(f"更新中にエラーが発生しました: {str(e)}", "danger")

    return render_template("student/edit.html", student=student, staff_list=Staff.query.all(), city_list=SAITAMA_MUNICIPALITIES)


@student_bp.route('/attendance')
@login_required
def attendance_list():
    """Show the attendance list for a specific date."""
    # 1. クエリパラメータから日付を取得
    date_str = request.args.get('date')
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = datetime.now().date()

    # 2. その日の学習録（出席データ）をすべて取得
    # student や staff のリレーションをまとめて読み込む(joinedload)と処理が高速になります
    logs = LearningRecord.query.options(
        joinedload(LearningRecord.student),
        joinedload(LearningRecord.staff)
    ).filter_by(lesson_date=target_date).all()

    # 3. 国籍ごとに生徒をグループ化する辞書を作成
    # 構造: { "ベトナム": [生徒1, 生徒2], "ミャンマー": [生徒3] }
    grouped_students = defaultdict(list)
    
    for log in logs:
        student = log.student
        if student:
            # テンプレート側で表示しやすいように、担当スタッフの名前を一時的に生徒オブジェクトに持たせる
            student.assigned_staff_name = log.staff.name if log.staff else "自習"
            # 国籍をキーにしてグループに追加
            country = student.country_of_origin or "不明"
            grouped_students[country].append(student)

    return render_template(
        'student/attendance.html',
        target_date=target_date,
        grouped_students=dict(grouped_students), # 扱いやすいように通常の辞書型に変換
        total_count=len(logs)
    )
    

# PDF生成用の定数
PDF_HEADER_ROW_HEIGHT = 10
PDF_DATA_ROW_HEIGHT = 20
PDF_COL_WIDTH_NO = 15
PDF_COL_WIDTH_NAME = 60
PDF_COL_WIDTH_PHOTO = 20
PDF_COL_WIDTH_COUNTRY = 30
PDF_COL_WIDTH_STAFF = 30
PDF_COL_WIDTH_NEXT_DATE = 30
PDF_ROWS_PER_PAGE = 12 # 1ページあたりのデータ行数
PDF_NEXT_DATE_OFFSET_DAYS = 8 # 次回日付の計算オフセット


# FPDFに日本語フォントを読み込ませるための準備
# 1. プロジェクト内に .ttf フォントファイルを用意してください（例: fonts/ipaexg.ttf）
# 2. Vercelの制限を回避するため、外部コンパイルが不要なこの構成で動かします

class PDF(FPDF):
    def header(self):
        """Set PDF header."""
        self.set_font("Arial", 'B', 12)
        self.cell(0, 10, 'Attendance List', 0, 1, 'C')


def add_pdf_table_header(pdf, next_date_header):
    """PDFテーブルのヘッダー行を追加します。"""
    pdf.cell(PDF_COL_WIDTH_NO, PDF_HEADER_ROW_HEIGHT, "No", border=1)
    pdf.cell(PDF_COL_WIDTH_NAME, PDF_HEADER_ROW_HEIGHT, "Name", border=1)
    pdf.cell(PDF_COL_WIDTH_PHOTO, PDF_HEADER_ROW_HEIGHT, "Photo", border=1)
    pdf.cell(PDF_COL_WIDTH_COUNTRY, PDF_HEADER_ROW_HEIGHT, "Country", border=1)
    pdf.cell(PDF_COL_WIDTH_STAFF, PDF_HEADER_ROW_HEIGHT, "Staff", border=1)
    pdf.cell(PDF_COL_WIDTH_NEXT_DATE, PDF_HEADER_ROW_HEIGHT, next_date_header, border=1)
    pdf.ln()


@student_bp.route('/attendance/download-pdf')
@login_required
def download_attendance_pdf():
    """Generate and download the attendance list as a PDF."""
    date_str = request.args.get('date')
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now().date()
    
    logs = LearningRecord.query.options(
        joinedload(LearningRecord.student),
        joinedload(LearningRecord.staff)
    ).filter_by(lesson_date=target_date).all()
    
    # PDF生成
    pdf = PDF()
    pdf.add_page()
    
    # 簡易テーブル作成（FPDFのCellを使用）
    font_path = os.path.join(current_app.root_path, 'fonts', 'ipaexg.ttf')
    pdf.add_font("IPAexGothic", "", font_path, uni=True)
    pdf.set_font("IPAexGothic", size=10)

    next_date_header = (target_date + timedelta(days=PDF_NEXT_DATE_OFFSET_DAYS)).strftime('%Y-%m-%d')
    add_pdf_table_header(pdf, next_date_header)
    
    count = 0
    for log in logs:
        if count > 0 and count % PDF_ROWS_PER_PAGE == 0:
            pdf.add_page()
            pdf.set_font("IPAexGothic", size=10) # フォント設定を再度適用
            add_pdf_table_header(pdf, next_date_header)

        student = log.student
        if student:
            count += 1
            # joinedloadで取得済みなので、直接アクセス
            staff_name = log.staff.name if log.staff else "未定"
            
            # 画像データはVercelのメモリ制限を避けるため、今回は一旦テキスト情報のみで出力
            # FPDFに画像を追加する場合は pdf.image() を使いますが、URLからは直接読み込めないため
            # 必要であれば事前にキャッシュフォルダへ保存する等のロジックが必要です
            row_height = 20
            
            pdf.cell(15, row_height, str(count), border=1)
            pdf.cell(PDF_COL_WIDTH_NAME, PDF_DATA_ROW_HEIGHT, student.name_kana, border=1) # 文字数制限

            # 画像枠（セル）を必ず作成し、カーソル位置を正しく制御
            x_pos = pdf.get_x()
            y_pos = pdf.get_y()
            pdf.cell(PDF_COL_WIDTH_PHOTO, PDF_DATA_ROW_HEIGHT, "", border=1)

            if student.face_photo_path:
                try:
                    response = requests.get(student.face_photo_path, timeout=5)
                    if response.status_code == 200:
                        image_data = io.BytesIO(response.content)
                        # 画像をセルの中央に配置
                        pdf.image(
                            image_data,
                            x=x_pos + (PDF_COL_WIDTH_PHOTO - (PDF_DATA_ROW_HEIGHT - 2)) / 2, # セル幅 - (画像高さ) / 2
                            y=y_pos + 1,
                            w=PDF_DATA_ROW_HEIGHT - 2, # 画像の幅をセルの高さに合わせて調整（正方形を想定）
                            h=PDF_DATA_ROW_HEIGHT - 2
                        )
                    else:
                        current_app.logger.warning(f"Failed to fetch image: Status {response.status_code}")
                except Exception as e:
                    current_app.logger.error(f"Image download error: {e}")

            pdf.cell(30, row_height, student.country_of_origin or "N/A", border=1)
            pdf.cell(PDF_COL_WIDTH_STAFF, PDF_DATA_ROW_HEIGHT, staff_name, border=1)
            pdf.cell(PDF_COL_WIDTH_NEXT_DATE, PDF_DATA_ROW_HEIGHT, "", border=1)
            pdf.ln()
    # ストリームに出力
    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_data = pdf_buffer.getvalue()
    
    # 応答を作成
    response = make_response(pdf_data)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=attendance_{target_date}.pdf'
    
    return response