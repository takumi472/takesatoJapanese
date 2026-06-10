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


# 階層化された地域データ構造 (例として関東地方の一部を定義)
REGION_DATA = {
    "北海道": {
        "北海道": ["札幌市", "函館市", "小樽市", "旭川市", "室蘭市", "釧路市", "帯広市", "北見市"]
    },
    "東北": {
        "青森県": ["青森市", "弘前市", "八戸市"],
        "岩手県": ["盛岡市", "釜石市"],
        "宮城県": ["仙台市", "石巻市", "大崎市"],
        "秋田県": ["秋田市", "横手市"],
        "山形県": ["山形市", "米沢市", "酒田市"],
        "福島県": ["福島市", "会津若松市", "郡山市", "いわき市"]
    },
    "関東": {
        "茨城県": ["水戸市", "日立市", "つくば市"],
        "栃木県": ["宇都宮市", "足利市", "栃木市"],
        "群馬県": ["前橋市", "高崎市", "桐生市"],
        "埼玉県": [
            "さいたま市西区", "さいたま市北区", "さいたま市大宮区", "さいたま市見沼区",
            "さいたま市中央区", "さいたま市桜区", "さいたま市浦和区", "さいたま市南区",
            "さいたま市緑区", "さいたま市岩槻区", "川口市", "春日部市", "上尾市", "越谷市",
            "川越市", "所沢市", "草加市", "朝霞市", "志木市", "和光市", "新座市", "桶川市", "北本市",
            "鴻巣市", "久喜市", "蓮田市", "幸手市", "白岡市", "杉戸町", "宮代町"
        ],
        "千葉県": ["千葉市", "市川市", "船橋市", "松戸市", "柏市"],
        "東京都": [
            "千代田区", "中央区", "港区", "新宿区", "文京区", "台東区", "墨田区", "江東区",
            "品川区", "目黒区", "大田区", "世田谷区", "渋谷区", "中野区", "杉並区", "豊島区",
            "北区", "荒川区", "板橋区", "練馬区", "足立区", "葛飾区", "江戸川区", "八王子市", "立川市"
        ],
        "神奈川県": ["横浜市", "川崎市", "相模原市", "藤沢市", "横須賀市"]
    },
    "中部": {
        "新潟県": ["新潟市", "長岡市", "上越市"],
        "富山県": ["富山市", "高岡市"],
        "石川県": ["金沢市", "小松市"],
        "福井県": ["福井市", "敦賀市"],
        "山梨県": ["甲府市", "大月市"],
        "長野県": ["長野市", "松本市", "上田市"],
        "岐阜県": ["岐阜市", "大垣市"],
        "静岡県": ["静岡市", "浜松市", "沼津市", "熱海市"],
        "愛知県": ["名古屋市", "豊田市", "岡崎市", "一宮市"]
    },
    "近畿": {
        "三重県": ["津市", "四日市市", "伊勢市"],
        "滋賀県": ["大津市", "彦根市"],
        "京都府": ["京都市", "宇治市", "舞鶴市"],
        "大阪府": ["大阪市", "堺市", "東大阪市", "豊中市", "枚方市"],
        "兵庫県": ["神戸市", "姫路市", "尼崎市", "明石市", "西宮市"],
        "奈良県": ["奈良市", "橿原市"],
        "和歌山県": ["和歌山市", "田辺市"]
    },
    "中国": {
        "鳥取県": ["鳥取市", "米子市"],
        "島根県": ["松江市", "出雲市"],
        "岡山県": ["岡山市", "倉敷市"],
        "広島県": ["広島市", "呉市", "福山市"],
        "山口県": ["山口市", "下関市", "岩国市"]
    },
    "四国": {
        "徳島県": ["徳島市", "鳴門市"],
        "香川県": ["高松市", "丸亀市"],
        "愛媛県": ["松山市", "今治市"],
        "高知県": ["高知市", "四万十市"]
    },
    "九州": {
        "福岡県": ["福岡市", "北九州市", "久留米市", "飯塚市"],
        "佐賀県": ["佐賀市", "唐津市"],
        "長崎県": ["長崎市", "佐世保市"],
        "熊本県": ["熊本市", "八代市"],
        "大分県": ["大分市", "別府市"],
        "宮崎県": ["宮崎市", "延岡市"],
        "鹿児島県": ["鹿児島市", "鹿屋市"],
        "沖縄県": ["那覇市", "沖縄市", "石垣市"]
    }
}



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
            return render_template("student/create.html", staff_list=Staff.query.all(), region_data=REGION_DATA, google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"))

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

    return render_template("student/create.html", staff_list=staff_list, region_data=REGION_DATA, google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"))


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
                return render_template("student/edit.html", student=student, staff_list=Staff.query.all(), region_data=REGION_DATA, google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"))
            if face_photo_path:
                student.face_photo_path = face_photo_path

        try:
            db.session.commit()
            flash(f"{student.name_kana} さんの情報を更新しました。", "success")
            return redirect(url_for("student.student_list"))
        except Exception as e:
            db.session.rollback()
            flash(f"更新中にエラーが発生しました: {str(e)}", "danger")
    return render_template("student/edit.html", student=student, staff_list=Staff.query.all(), region_data=REGION_DATA, google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"))


@student_bp.route('/attendance')
@login_required
def attendance_list():
    # 1. クエリパラメータから日付を取得（指定がなければ今日の日付）
    date_str = request.args.get('date')
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = datetime.now().date()

    # 2. その日の学習録（出席データ）をすべて取得
    # student や staff のリレーションをまとめて読み込む(joinedload)と処理が高速になります
    logs = LearningRecord.query.filter_by(lesson_date=target_date).all()

    # 3. 国籍ごとに生徒をグループ化する辞書を作成
    # 構造: { "ベトナム": [生徒1, 生徒2], "ミャンマー": [生徒3] }
    grouped_students = defaultdict(list)
    
    for log in logs:
        student = log.student
        if student:
            # テンプレート側で表示しやすいように、担当スタッフの名前を一時的に生徒オブジェクトに持たせる
            # print(dir(log.staff_id))
            staff_info = User.query.filter_by(id=log.staff_id).first().name
            student.assigned_staff_name =  staff_info if staff_info else "自習"
            # 国籍をキーにしてグループに追加
            country = student.country_of_origin or "不明"
            grouped_students[country].append(student)

    return render_template(
        'student/attendence.html',
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
        self.set_font("Arial", 'B', 12)
        self.cell(0, 10, 'Attendance List', 0, 1, 'C')

def get_pdf_image(image_path_or_url):
    if not image_path_or_url: return ""
    if image_path_or_url.startswith(('http://', 'https://')):
        try:
            response = requests.get(image_path_or_url, timeout=5)
            if response.status_code == 200:
                base64_data = base64.b64encode(response.content).decode('utf-8')
                mime_type = "image/png" if "png" in image_path_or_url.lower() else "image/jpeg"
                return f"data:{mime_type};base64,{base64_data}"
        except Exception: pass
    return ""

@student_bp.route('/attendance/download-pdf')
@login_required
def download_attendance_pdf():
    date_str = request.args.get('date')
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now().date()
    
    logs = LearningRecord.query.filter_by(lesson_date=target_date).all()
    
    # PDF生成
    pdf = PDF()
    pdf.add_page()
    
    # 簡易テーブル作成（FPDFのCellを使用）
    font_path = os.path.join(current_app.root_path, 'fonts', 'ipaexg.ttf')
    pdf.add_font("IPAexGothic", "", font_path, uni=True)
    pdf.set_font("IPAexGothic", size=10)

    next_date = datetime.strptime(date_str, '%Y-%m-%d').date() + timedelta(days=8) if date_str else datetime.now().date() + timedelta(days=8)
    # headers = ["No", "Name", "", "Country", "Staff", str(next_date)]
    pdf.cell(15, 10, "No", border=1)
    pdf.cell(60, 10, "Name", border=1)
    pdf.cell(20, 10, "Photo", border=1)
    pdf.cell(30, 10, "Country", border=1)
    pdf.cell(30, 10, "Staff", border=1)
    pdf.cell(30, 10, str(next_date), border=1)
    pdf.ln()
    
    count = 0
    for log in logs:
        if (count % 12 == 0 and count != 0):
            pdf.cell(15, 10, "No", border=1)
            pdf.cell(60, 10, "Name", border=1)
            pdf.cell(20, 10, "Photo", border=1)
            pdf.cell(30, 10, "Country", border=1)
            pdf.cell(30, 10, "Staff", border=1)
            pdf.cell(30, 10, str(next_date), border=1)
            pdf.ln()
        student = log.student
        if student:
            count += 1
            staff_name = User.query.get(log.staff_id).name if log.staff_id else "未定"
            
            # 画像データはVercelのメモリ制限を避けるため、今回は一旦テキスト情報のみで出力
            # FPDFに画像を追加する場合は pdf.image() を使いますが、URLからは直接読み込めないため
            # 必要であれば事前にキャッシュフォルダへ保存する等のロジックが必要です
            row_height = 20
            
            pdf.cell(15, row_height, str(count), border=1)
            pdf.cell(60, row_height, student.name_kana, border=1) # 文字数制限
            try:
                response = requests.get(student.face_photo_path, timeout=5)
                if response.status_code == 200:
                    # 2. メモリ上に画像を読み込む
                    image_data = io.BytesIO(response.content)
                    x_pos = pdf.get_x()
                    y_pos = pdf.get_y()
                    cell_width = 20
                    pdf.cell(cell_width, row_height, "", border=1)
        
                    # 3. PDFに画像を配置
                    # x, y は枠内の位置、wは画像幅
                    pdf.image(
                        image_data,
                        x=x_pos + 1, 
                        y=y_pos + 1, 
                        w=cell_width - 2, 
                        h=row_height - 2
                    )
                    # pdf.set_x(x_pos + cell_width)
                else:
                    print(f"画像取得失敗: ステータスコード {response.status_code}")
            except Exception as e:
                print(f"画像ダウンロードエラー: {e}")
            # pdf.image(student.face_photo_path, x=40 + 1, y=40 + 1, w=40 - 2, h=40 - 2)
            # pdf.cell(40, 40, get_pdf_image(student.face_photo_path), border=1)
            pdf.cell(30, row_height, student.country_of_origin or "N/A", border=1)
            pdf.cell(30, row_height, staff_name, border=1)
            pdf.cell(30, row_height, "", border=1)
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