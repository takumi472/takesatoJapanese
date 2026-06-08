# app/student/routes.py
from datetime import datetime, timedelta
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import User, Student, LearningRecord
from app.decorators import roles_required
import cloudinary
import cloudinary.uploader

student_bp = Blueprint("student", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


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

    return render_template("student/create.html")


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

    # GETリクエスト時は、現在の生徒データとosモジュール（HTML内判定用）を渡して表示
    return render_template("student/edit.html", student=student, os=os)
