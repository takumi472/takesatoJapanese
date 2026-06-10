import os
import time
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user, login_required
import cloudinary
import cloudinary.uploader

from app import db
from app.models import Meeting, Attachment

# ブループリントの定義
meeting_bp = Blueprint('meeting', __name__, url_prefix='/meeting')

PDF_EXTENSION = '.pdf'

# Cloudinaryの設定は、通常、アプリケーションの初期化時に行われます（例: app/__init__.pyまたはconfig.py）。
# ここでは、current_app.configから設定が読み込まれることを想定しています。
# 例: current_app.config['CLOUDINARY_CLOUD_NAME'], current_app.config['CLOUDINARY_API_KEY'], etc.
# Cloudinaryの初期化
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME') or current_app.config.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY') or current_app.config.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET') or current_app.config.get('CLOUDINARY_API_SECRET'),
    secure = True
)

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
                    original_name = file.filename # オリジナルファイル名
                    
                    # Cloudinaryにファイルをアップロード
                    # folderパラメータでCloudinary上のフォルダを指定できます
                    upload_result = cloudinary.uploader.upload(
                        file, 
                        folder="takesato_meeting_attachments",
                        resource_type="auto"
                    )
                    save_name = upload_result['secure_url'] # CloudinaryのURLを保存
                    
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

            # 既存の添付ファイルの削除処理
            delete_ids = request.form.getlist('delete_attachments')
            for aid in delete_ids:
                attachment = Attachment.query.get(int(aid))
                if attachment and attachment.meeting_id == meeting.id:
                    # Cloudinaryからファイルを削除
                    try:
                        # URLからpublic_idを抽出 (例: .../takesato_meeting_attachments/xxxx.pdf)
                        filename_with_ext = attachment.filename.split('/')[-1]
                        public_id_no_ext = os.path.splitext(filename_with_ext)[0]
                        full_public_id = f"takesato_meeting_attachments/{public_id_no_ext}"
                        # PDFなどのリソースは通常 'image' として扱われます
                        cloudinary.uploader.destroy(full_public_id)
                    except Exception as ce:
                        current_app.logger.warning(f"Cloudinary deletion failed for {attachment.filename}: {ce}")
                    
                    db.session.delete(attachment)

            # 編集時も新規添付ファイルがあればCloudinaryにアップロード
            files = request.files.getlist('pdf_files')
            for file in files:
                if file and file.filename.endswith(PDF_EXTENSION):
                    original_name = file.filename
                    upload_result = cloudinary.uploader.upload(
                        file, 
                        folder="takesato_meeting_attachments",
                        resource_type="auto"
                    )
                    save_name = upload_result['secure_url']
                    new_attach = Attachment(filename=save_name, original_name=original_name, meeting=meeting)
                    db.session.add(new_attach)
            
            db.session.commit()
            flash('会議記録を更新しました。', 'success')
            return redirect(url_for('meeting.detail_meeting', id=id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating meeting {id}: {e}", exc_info=True)
            flash(f'更新中にエラーが発生しました: {str(e)}', 'danger')

    return render_template('meeting/form.html', meeting=meeting)
