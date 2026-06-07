# app/student/routes.py
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import User, Student, LearningRecord
from app.decorators import roles_required

student_bp = Blueprint('student', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@student_bp.route('/create', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'staff')
def create_student():
    if request.method == 'POST':
        # --- 1. 画像ファイルの保存処理 ---
        file = request.files.get('face_photo')
        if not file or file.filename == '':
            flash('顔写真をアップロードしてください。', 'danger')
            return render_template('student/create.html')
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            if os.environ.get('VERCEL'):
                # Vercel環境なら、唯一書き込みが許されている /tmp フォルダを使う
                upload_folder = '/tmp'
            else:
                # ローカル環境なら、これまで通り static/uploads フォルダを使う
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            file.save(os.path.join(upload_folder, filename))
            face_photo_path = f'static/uploads/{filename}'
        else:
            flash('許可されていないファイル形式です。', 'danger')
            return render_template('student/create.html')

        try:
            # --- 2. Student テーブルへの直接保存 ---
            new_student = Student(
                face_photo_path=face_photo_path,
                name_kana=request.form.get('student_name_kana'),
                country_of_origin=request.form.get('country_of_origin'),
                native_language=request.form.get('native_language'),
                other_languages=request.form.get('other_languages'),
                occupation=request.form.get('occupation'),
                residential_area=request.form.get('residential_area'),
                jlpt_level=request.form.get('jlpt_level'),
                learning_purpose=request.form.get('learning_purpose'),
                life_troubles=request.form.get('life_troubles'),
                how_knew_class=request.form.get('how_knew_class'),
                how_knew_class_other=request.form.get('how_knew_class_other')
            )
            db.session.add(new_student)
            db.session.flush() # new_student.id を確定させる

            # --- 3. LearningRecord（本日の学習記録）への保存 ---
            today_content = request.form.get('today_learning_content')
            if today_content:
                new_record = LearningRecord(
                    student_id=new_student.id, # 確定した生徒IDを紐付け
                    staff_id=current_user.id,  # ログイン中のスタッフID
                    today_learning_content=today_content
                )
                db.session.add(new_record)

            db.session.commit()
            flash('受講生の新規登録と学習記録の保存が完了しました！', 'success')
            return redirect(url_for('student.student_list'))

        except Exception as e:
            db.session.rollback()
            flash(f'エラーが発生しました: {str(e)}', 'danger')

    return render_template('student/create.html')

@student_bp.route('/')
@login_required
def student_list():
    # studentsテーブルから全受講生データを取得
    all_students = Student.query.order_by(Student.id.asc()).all()
    
    # テンプレートに student_list としてデータを引き渡す
    return render_template('student/list.html', student_list=all_students)

# app/student/routes.py 内
@student_bp.route('/<int:id>/update', methods=['GET', 'POST'])
def update_student(id): # 関数名が「update_student」で、引数が「id」になっている必要があります
    # 1. 指定されたIDの生徒をPostgreSQLから厳密に取得（なければ404）
    student = Student.query.get_or_404(id)

    if request.method == 'POST':
        # 2. フォームから送られてきた新しい値で上書き
        student.name_kana = request.form.get('name_kana')
        student.country_of_origin = request.form.get('country_of_origin')
        student.native_language = request.form.get('native_language')
        student.other_languages = request.form.get('other_languages')
        student.occupation = request.form.get('occupation')
        student.residential_area = request.form.get('residential_area')
        student.jlpt_level = request.form.get('jlpt_level')
        student.learning_purpose = request.form.get('learning_purpose')
        student.life_troubles = request.form.get('life_troubles')
        student.how_knew_class = request.form.get('how_knew_class')
        student.how_knew_class_other = request.form.get('how_knew_class_other')

        # 3. 画像ファイルが新しくアップロードされた場合のみ処理
        file = request.files.get('face_photo')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            
            # Vercel環境かローカル環境かで保存先を変更（Read-only対策）
            if os.environ.get('VERCEL'):
                upload_folder = '/tmp'
            else:
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
                
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
                
            file.save(os.path.join(upload_folder, filename))
            # 新しい写真のファイル名に更新
            student.face_photo_path = filename

        # 4. データベースの変更を確定（コミット）
        try:
            db.session.commit()
            flash(f'{student.name_kana} さんの情報を更新しました。', 'success')
            return redirect(url_for('student.student_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'更新中にエラーが発生しました: {str(e)}', 'danger')

    # GETリクエスト時は、現在の生徒データとosモジュール（HTML内判定用）を渡して表示
    return render_template('student/edit.html', student=student, os=os)