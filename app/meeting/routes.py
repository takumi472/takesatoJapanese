import os
import time
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models import Meeting, Attachment

# ブループリントの定義
meeting_bp = Blueprint('meeting', __name__, url_prefix='/meeting')

# 定数定義
UPLOAD_FOLDER_DEFAULT = 'app/static/uploads'
PDF_EXTENSION = '.pdf'

# Helper function to ensure upload folder exists
def _ensure_upload_folder_exists(app_instance):
    upload_path = app_instance.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER_DEFAULT)
    if not os.path.exists(upload_path):
        os.makedirs(upload_path)
        app_instance.logger.info(f"Created upload folder: {upload_path}")

@meeting_bp.route('/')
@login_required
def meeting_list():
    """List all meetings ordered by date."""
    meetings = Meeting.query.order_by(Meeting.date.desc()).all()
    return render_template('meeting/list.html', meetings=meetings)


@meeting_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_meeting():
    """Handle the creation of a new meeting record."""
    if request.method == 'POST':
        # Ensure upload folder exists before attempting to save files
        _ensure_upload_folder_exists(current_app)

        try:
            # 日付文字列をパースして Date オブジェクトに変換
            date_str = request.form.get('date')
            meeting_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now().date()
            
            new_m = Meeting(
                title=request.form['title'], 
                date=meeting_date, 
                content=request.form['content'],
                created_by=current_user.id
            )
            # まず親レコード（Meeting）をセッションに追加して追跡対象にする
            db.session.add(new_m)

            files = request.files.getlist('pdf_files')
            for file in files:
                if file and file.filename.endswith(PDF_EXTENSION):
                    original_name = file.filename
                    # 保存時に重複しないようID等を付与
                    save_name = f"{int(time.time())}_{secure_filename(original_name)}"
                    upload_path = current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER_DEFAULT)
                    file.save(os.path.join(upload_path, save_name))
                    
                    # 添付ファイル情報をDBに追加
                    new_attach = Attachment(filename=save_name, original_name=original_name, meeting=new_m)
                    db.session.add(new_attach)
            
            # 1回のみのコミットで全ての関連レコードをアトミックに保存
            db.session.commit()
            flash('会議記録を登録しました。', 'success')
            return redirect(url_for('meeting.meeting_list'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating meeting: {e}", exc_info=True)
            flash(f'登録中にエラーが発生しました: {str(e)}', 'danger')

    return render_template('meeting/form.html')


@meeting_bp.route('/<int:id>')
@login_required
def detail_meeting(id):
    """Show meeting details."""
    meeting = Meeting.query.get_or_404(id)
    return render_template('meeting/detail.html', meeting=meeting)


@meeting_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_meeting(id):
    """Edit an existing meeting record."""
    # Consider using a decorator for role-based access control if this check becomes common
    if current_user.role != 'admin':
        flash('編集権限がありません。', 'danger')
        return redirect(url_for('meeting.detail_meeting', id=id))

    meeting = Meeting.query.get_or_404(id)
    if request.method == 'POST':
        try:
            date_str = request.form.get('date')
            if date_str:
                meeting.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            meeting.title = request.form['title']
            meeting.content = request.form['content']
            
            db.session.commit()
            flash('会議記録を更新しました。', 'success')
            return redirect(url_for('meeting.detail_meeting', id=id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating meeting {id}: {e}", exc_info=True)
            flash(f'更新中にエラーが発生しました: {str(e)}', 'danger')

    return render_template('meeting/form.html', meeting=meeting)
