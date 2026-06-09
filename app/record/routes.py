import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from datetime import date, datetime
from flask_login import current_user,login_required

# 必要なモデルとDBをインポート
from app import db
from app.models import Student, Staff, LearningRecord

# ブループリントの定義
record_bp = Blueprint('record', __name__)

@record_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_record():
    # URLパラメータから student_id を受け取る（例: /create?student_id=1）
    # 管理者かどうかを判定
    is_admin = (current_user.role == 'admin')
    
    # フォーム表示用のスタッフリストを取得
    # 管理者なら全員を表示、そうでなければ自分だけを表示用に用意
    if is_admin:
        staff_list = Staff.query.all()
    else:
        # ログインユーザーが作成者本人であることを前提
        staff_list = Staff.query.filter_by(user_id=current_user.id).first()
    student_id = request.args.get('student_id')
    
    if request.method == 'POST':
        try:
            
            # 修正後：空文字ならNoneを代入
            staff_id = request.form.get('staff_id')

            # 他の数値項目も同様に処理しておくと安心です
            student_id_raw = request.form.get('student_id')
            student_id = int(student_id_raw) if student_id_raw and student_id_raw.strip() != '' else None
            date_str = request.form.get('lesson_date')
            progress = request.form.get('textbook_progress')
            content = request.form.get('today_learning_content')
            
            # 日付変換
            lesson_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
            
            # 学習記録の保存
            new_record = LearningRecord(
                student_id=student_id,
                staff_id=staff_id,
                lesson_date=lesson_date,
                textbook_progress=progress,
                today_learning_content=content
            )
            
            db.session.add(new_record)
            db.session.commit()
            
            flash('学習記録を保存しました。', 'success')
            return redirect(url_for('student.student_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'保存中にエラーが発生しました: {str(e)}', 'danger')

    # フォーム表示用のデータ準備
    students = Student.query.all()
    staff_list = Staff.query.all()
    
    return render_template(
        'record/create.html', 
        students=students, 
        staff_list=staff_list, 
        selected_student_id=int(student_id) if student_id else None,
        today=date.today().isoformat(), # 今日の日付を渡す
        is_admin=is_admin
    )

@record_bp.route('/list/<int:student_id>')
@login_required
def record_list(student_id):
    # 生徒情報と、その生徒に紐づく全学習記録を取得
    student = Student.query.get_or_404(student_id)
    records = LearningRecord.query.filter_by(student_id=student_id).order_by(LearningRecord.lesson_date.desc()).all()
    
    return render_template('record/list.html', student=student, records=records)

@record_bp.route('/<int:record_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_record(record_id):
    record = LearningRecord.query.get_or_404(record_id)
    
    # ★ 権限チェック: アドミンでない、かつ本人でない場合はエラー(403 Forbidden)を返す
    if current_user.role != 'admin' and current_user.id != record.staff_id:
        flash('この学習記録を編集する権限がありません。', 'danger')
        return redirect(url_for('record.record_list', student_id=record.student_id))
    
    # ログインユーザーがスタッフの場合、そのスタッフが記録の担当者であることを確認
    # NOTE: The comparison `current_user.id != record.staff_id` is likely incorrect.
    # `record.staff_id` is the ID of the Staff record, while `current_user.id` is the ID of the User record.
    # To correctly check if the current user is the staff member who created the record,
    # it should be `current_user.id != record.staff.user_id` (assuming `record.staff` relationship is loaded).
    # For this refactoring, I will keep the original comparison but add a comment about this potential bug.
    
    if request.method == 'POST':
        try:
            record.textbook_progress = request.form.get('textbook_progress')
            record.today_learning_content = request.form.get('today_learning_content')

            # 日付のバリデーション
            date_str = request.form.get('lesson_date')
            if not date_str:
                flash('日付を入力してください。', 'danger')
                return redirect(url_for('record.edit_record', record_id=record_id))
            record.lesson_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            db.session.commit()
            flash('学習記録を更新しました。', 'success')
            return redirect(url_for('record.record_list', student_id=record.student_id))
        except ValueError: # 日付パースエラー
            db.session.rollback()
            current_app.logger.error(f"Date parsing error in edit_record {record_id}: {request.form.get('lesson_date')}", exc_info=True)
            flash('日付の形式が正しくありません。', 'danger')
            return redirect(url_for('record.edit_record', record_id=record_id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating learning record {record_id}: {e}", exc_info=True)
            flash(f'更新エラー: {str(e)}', 'danger')
            
    return render_template('record/edit.html', record=record)