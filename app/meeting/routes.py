import os
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db # アプリケーションのdbインスタンスをインポート
from app.models import Meeting, Attachment # 定義したミーティングモデルをインポート

# ブループリントの定義
meeting_bp = Blueprint('meeting', __name__, url_prefix='/meeting')

# ファイルアップロード先のディレクトリ
UPLOAD_FOLDER = 'app/static/uploads'

@meeting_bp.route('/')
@login_required
def meeting_list():
    meetings = Meeting.query.order_by(Meeting.date.desc()).all()
    return render_template('meeting/list.html', meetings=meetings)

@meeting_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_meeting():
    if request.method == 'POST':
        new_m = Meeting(title=request.form['title'], date=request.form['date'], content=request.form['content'])
        files = request.files.getlist('pdf_files')
        for file in files:
            if file and file.filename.endswith('.pdf'):
                original_name = file.filename
                # 保存時に重複しないようID等を付与
                save_name = f"{int(time.time())}_{secure_filename(original_name)}"
                file.save(os.path.join(UPLOAD_FOLDER, save_name))
                
                # 添付ファイル情報をDBに追加
                new_attach = Attachment(filename=save_name, original_name=original_name, meeting=new_m)
                db.session.add(new_attach)
        
        db.session.commit()
        db.session.add(new_m)
        db.session.commit()
        return redirect(url_for('meeting.meeting_list'))
    return render_template('meeting/form.html')

@meeting_bp.route('/<int:id>')
@login_required
def detail_meeting(id):
    meeting = Meeting.query.get_or_404(id)
    return render_template('meeting/detail.html', meeting=meeting)

@meeting_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_meeting(id):
    if current_user.role != 'admin':
        flash('編集権限がありません。', 'danger')
        return redirect(url_for('meeting.detail_meeting', id=id))

    meeting = Meeting.query.get_or_404(id)
    if request.method == 'POST':
        meeting.title = request.form['title']
        meeting.date = request.form['date']
        meeting.content = request.form['content']
        db.session.commit()
        return redirect(url_for('meeting.detail_meeting', id=id))
    return render_template('meeting/form.html', meeting=meeting)