# app/student/routes.py
from datetime import datetime, timedelta
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import User, Student, LearningRecord, Staff
from app.decorators import roles_required
import cloudinary
import cloudinary.uploader

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
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@student_bp.route("/create", methods=["GET", "POST"])
@login_required
@roles_required("admin", "staff")
def create_student():
    if request.method == "POST":
        # --- 1. 画像ファイルの保存処理 ---
        file = request.files.get("face_photo")
        if not file or file.filename == "":
            flash("顔写真をアップロードしてください。", "danger")
            return render_template("student/create.html")

        if file and allowed_file(file.filename):
            # 1. サーバーの static ではなく、クラウド（Cloudinary）に直接アップロード
            upload_result = cloudinary.uploader.upload(
                file,
                folder = "students",
                eager=[
                    {
                        "crop": "thumb",      # 顔がきれいに収まるサムネイルモード
                        "gravity": "face",    # AIによる顔認識（高精度なら "adv_face"）
                        "zoom": 0.7,          # 顔を大きくする（数字が小さいほどドアップ）
                        "width": 200,         # 最終的な横幅
                        "height": 200,        # 最終的な縦幅
                        "fetch_format": "auto", # PWA・スマホ用に自動軽量化
                        "quality": "auto"       # 画質を自動最適化
                    }
                ]
            )
            # 2. クラウド上の画像URL（https://res.cloudinary.com/...）を取得
            face_photo_path = upload_result.get('eager')[0].get('secure_url')
        else:
            flash("許可されていないファイル形式です。", "danger")
            return render_template("student/create.html")

        try:
            # --- 2. Student テーブルへの直接保存 ---
            new_student = Student(
                face_photo_path=face_photo_path,
                name_kana=request.form.get("student_name_kana"),
                country_of_origin=request.form.get("country_of_origin"),
                native_language=request.form.get("native_language"),
                other_languages=request.form.get("other_languages"),
                occupation=request.form.get("occupation"),
                residential_area=request.form.get("residential_area"),
                jlpt_level=request.form.get("jlpt_level"),
                learning_purpose=request.form.get("learning_purpose"),
                life_troubles=request.form.get("life_troubles"),
                how_knew_class=request.form.get("how_knew_class"),
                how_knew_class_other=request.form.get("how_knew_class_other"),
            )
            db.session.add(new_student)
            db.session.flush()  # new_student.id を確定させる

            # --- 3. LearningRecord（本日の学習記録）への保存 ---
            today_content = request.form.get("today_learning_content")
            if today_content:
                new_record = LearningRecord(
                    student_id=new_student.id,  # 確定した生徒IDを紐付け
                    staff_id=current_user.id,  # ログイン中のスタッフID
                    today_learning_content=today_content,
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
    students = Student.query.all()
    
    # 2ヶ月前の基準日付を計算 (現在から60日前)
    # 「datetime.timedelta」ではなく「timedelta」にする
    two_months_ago = (datetime.now() - timedelta(days=60)).date()
    
    active_students = []     # 2ヶ月以内に学習録がある生徒
    inactive_students = []   # 最後の学習録から2ヶ月以上経っている生徒
    
    for student in students:
        # --- [前回の画像処理] ---
        # アップロード時にeager処理済みのURLがあればそれをそのまま使用
        # なければそのまま、あるいはフォールバック
        student.display_image = student.face_photo_path
        
        # --- [今回のグループ分け処理] ---
        # この生徒の「最新の学習録」を1件取得する
        # (study_logsリレーションがStudentモデルに定義されている前提)
        latest_log = LearningRecord.query.filter_by(student_id=student.id)\
                                  .order_by(LearningRecord.lesson_date.desc())\
                                  .first()
        
        if latest_log:
            student.latest_log_date = latest_log.lesson_date
            # 最新の学習録が2ヶ月前（基準日）より古いかどうか
            if latest_log.lesson_date < two_months_ago:
                inactive_students.append(student)
            else:
                active_students.append(student)
        else:
            # 学習録が1件も登録されていない生徒の扱い（今回は「2ヶ月以上空いている」側に分類）
            student.latest_log_date = None
            inactive_students.append(student)
            
    return render_template(
        'student/list.html', 
        active_students=active_students, 
        inactive_students=inactive_students
    )


# app/student/routes.py 内
@student_bp.route("/<int:id>/update", methods=["GET", "POST"])
def update_student(id):  # 関数名が「update_student」で、引数が「id」になっている必要があります
    # 1. 指定されたIDの生徒をPostgreSQLから厳密に取得（なければ404）
    student = Student.query.get_or_404(id)

    if request.method == "POST":
        # 2. フォームから送られてきた新しい値で上書き
        student.name_kana = request.form.get("name_kana")
        student.country_of_origin = request.form.get("country_of_origin")
        student.native_language = request.form.get("native_language")
        student.other_languages = request.form.get("other_languages")
        student.occupation = request.form.get("occupation")
        student.residential_area = request.form.get("residential_area")
        student.jlpt_level = request.form.get("jlpt_level")
        student.learning_purpose = request.form.get("learning_purpose")
        student.life_troubles = request.form.get("life_troubles")
        student.how_knew_class = request.form.get("how_knew_class")
        student.how_knew_class_other = request.form.get("how_knew_class_other")

        # 3. 画像ファイルが新しくアップロードされた場合のみ処理
        file = request.files.get("face_photo")
        if file and file.filename != "":
            upload_result = cloudinary.uploader.upload(
                file,
                folder = "students",
                eager=[
                    {
                        "crop": "thumb",      # 顔がきれいに収まるサムネイルモード
                        "gravity": "face",    # AIによる顔認識（高精度なら "adv_face"）
                        "zoom": 0.7,          # 顔を大きくする（数字が小さいほどドアップ）
                        "width": 200,         # 最終的な横幅
                        "height": 200,        # 最終的な縦幅
                        "fetch_format": "auto", # PWA・スマホ用に自動軽量化
                        "quality": "auto"       # 画質を自動最適化
                    }
                ]
            )
            # 2. クラウド上の画像URL（https://res.cloudinary.com/...）を取得
            face_photo_path = upload_result.get('eager')[0].get('secure_url')
            # 新しい写真のファイル名に更新
            student.face_photo_path = face_photo_path

        # 4. データベースの変更を確定（コミット）
        try:
            db.session.commit()
            flash(f"{student.name_kana} さんの情報を更新しました。", "success")
            return redirect(url_for("student.student_list"))
        except Exception as e:
            db.session.rollback()
            flash(f"更新中にエラーが発生しました: {str(e)}", "danger")
    staff_list = Staff.query.all()

    # GETリクエスト時は、現在の生徒データとosモジュール（HTML内判定用）を渡して表示
    return render_template("student/edit.html", student=student, os=os, staff_list=staff_list,city_list=SAITAMA_MUNICIPALITIES)

from flask import render_template, request
from app.models import Student, LearningRecord, Staff  # モデル名は実際の定義に合わせてください
from collections import defaultdict
from datetime import datetime

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
    
    
# import io
# import csv
# import pandas as pd
# from flask import render_template, make_response, request
# from app.models import LearningRecord, User
# from collections import defaultdict
# from datetime import datetime
# # ※PDF化ライブラリ（例: weasyprint や pdfkit など。ここではweasyprintの例）
# import base64
# import requests
# import os
# from flask import current_app
# # from xhtml2pdf import pisa
# import io
# import base64
# import requests
# from fpdf import FPDF

# # （前回のステップで作成した get_weasyprint_image などの関数はそのまま使えますが、名前を一般化しておきます）
# def get_pdf_image(image_path_or_url):
#     if not image_path_or_url: return ""
#     if image_path_or_url.startswith(('http://', 'https://')):
#         try:
#             response = requests.get(image_path_or_url, timeout=5)
#             if response.status_code == 200:
#                 base64_data = base64.b64encode(response.content).decode('utf-8')
#                 mime_type = "image/png" if "png" in image_path_or_url.lower() else "image/jpeg"
#                 return f"data:{mime_type};base64,{base64_data}"
#         except Exception: pass
#     return ""

# @student_bp.route('/attendance/download-pdf')
# @login_required
# def download_attendance_pdf():
#     # 1. 日付の指定を取得
#     date_str = request.args.get('date')
#     target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now().date()
#     next_date = datetime.strptime(date_str, '%Y-%m-%d').date() + timedelta(days=8) if date_str else datetime.now().date() + timedelta(days=8)

#     # 2. データベースから該当日の出席（学習録）を取得
#     logs = LearningRecord.query.filter_by(lesson_date=target_date).all()

#     # 3. データを一度フラットなリストに変換（CSVおよびデータフレーム用）
#     raw_data = []
#     country_counts = defaultdict(int)
    
#     count = 0
#     for log in logs:
#         student = log.student
#         if student:
#             country = student.country_of_origin or "未登録"
#             country_counts[country] += 1
            
#             staff_name = "未定"
#             if log.staff_id:
#                 staff_user = User.query.get(log.staff_id)
#                 staff_name = staff_user.name if staff_user else "不明"
            
#             # ★ ここでヘルパー関数を使ってBase64に一発変換！
#             base64_photo = get_pdf_image(student.face_photo_path)
#             count+=1  
#             raw_data.append({
#                 "内部連番": count,
#                 "顔写真": base64_photo,  # HTMLにテキストとして埋め込む
#                 "生徒の名前": student.name_kana,
#                 "国籍": country,
#                 "担当スタッフ": staff_name,
#                 next_date: ""
#             })
            

#     # 4. Pandasを使って国籍順に綺麗にソート
#     df = pd.DataFrame(raw_data)
#     if not df.empty:
#         df = df.sort_values(by=["内部連番", "国籍"]).reset_index(drop=True)
    
#     # ─── 【参考】もし背後でCSVファイル自体も同時に保存したい場合 ───
#     # df.to_csv(f"attendance_{target_date}.csv", index=False, encoding="utf-8-sig")

#     # 5. ソートされたCSVデータ（データフレーム）をPDF用のHTMLに流し込む
#     # html_string = render_template(
#     #     'student/attendance_pdf_template.html',
#     #     target_date=target_date,
#     #     data_rows=df.to_dict(orient='records')
#     # )

#     # 6. 【修正】WeasyPrintの代わりに xhtml2pdf (pisa) を使ってPDFを生成
#     pdf_buffer = io.BytesIO()
#     def df_to_pdf(df, output_path):
#         pdf = FPDF()
#         pdf.add_page()
#         pdf.set_font("Arial", size=10)
    
#         # テーブルヘッダーの描画
#         col_names = list(df.columns)
#         for col in col_names:
#             pdf.cell(40, 10, str(col), border=1)
#         pdf.ln()
    
#         # データ行の描画
#         for row in df.itertuples(index=False):
#             for val in row:
#                 pdf.cell(40, 10, str(val), border=1)
#             pdf.ln()
        
#         pdf.output(output_path)
#     # pisa_status = pisa.CreatePDF(html_string, dest=pdf_buffer, encoding='utf-8')
    
#     # if pisa_status.err:
#     #     return "PDF生成エラーが発生しました。", 500
#     df_to_pdf(df, 'output.pdf')
#     pdf_buffer.seek(0)
    
#     response = make_response(pdf_buffer.getvalue())
#     response.headers['Content-Type'] = 'application/pdf'
#     response.headers['Content-Disposition'] = f'attachment; filename=attendance_{target_date}.pdf'
#     return response

from flask import render_template, make_response, request, current_app
from app.models import LearningRecord, User
from collections import defaultdict
from datetime import datetime, timedelta
import io
import requests
from fpdf import FPDF
import base64
import requests
import io
from PIL import Image

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