# app/auth/routes.py
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import Interval, cast, func
from urllib.parse import urlparse
from datetime import datetime, timedelta
from app import db
from app.models import User, Student, Staff, Meeting, LearningRecord
from collections import Counter
from authlib.integrations.flask_client import OAuth

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()

# LINEの設定
line = oauth.register(
    name='line',
    client_id=os.environ.get('LINE_CLIENT_ID'),
    client_secret=os.environ.get('LINE_CLIENT_SECRET'),
    server_metadata_url='https://access.line.me/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid profile email',
        'id_token_signed_response_alg': 'HS256',
    },
)

def get_weekly_stats(start_date):
    """Helper to fetch weekly unique counts for students and staff."""
    # Note: date_trunc is PostgreSQL specific.
    student_query = db.session.query(
        func.date_trunc('week', LearningRecord.lesson_date).label('week'),
        func.count(LearningRecord.student_id.distinct()).label('count')
    ).filter(LearningRecord.lesson_date >= start_date).group_by('week')

    staff_query = db.session.query(
        func.date_trunc('week', LearningRecord.lesson_date).label('week'),
        func.count(LearningRecord.staff_id.distinct()).label('count')
    ).filter(LearningRecord.lesson_date >= start_date).group_by('week')

    return student_query.all(), staff_query.all()

@auth_bp.record_once
def on_load(state):
    oauth.init_app(state.app)

@auth_bp.route("/", methods=["GET", "POST"])
def auth_route():
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # 既にログイン済みの場合は、生徒一覧へリダイレクト
    if current_user.is_authenticated:
        return redirect(url_for("auth.dashboard"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # ユーザーの取得
        user = User.query.filter_by(username=username).first()

        # ユーザーが存在し、パスワードが一致するか確認
        if user and user.check_password(password):
            login_user(user, remember=True)  # セッション開始

            # 安全なリダイレクト先の確認
            next_page = request.args.get("next")
            if not next_page or urlparse(next_page).netloc != '':
                next_page = url_for("auth.dashboard")
            return redirect(next_page)
        else:
            flash("ユーザー名またはパスワードが正しくありません。", "danger")

    return render_template("auth/login.html")

@auth_bp.route("/login/line")
def login_line():
    """LINEの認証画面へリダイレクト"""
    redirect_uri = url_for('auth.line_callback', _external=True)
    return line.authorize_redirect(redirect_uri)

@auth_bp.route("/login/line/callback")
def line_callback():
    """LINEから戻ってきた後の処理"""
    error_msg = None
    try:
        token = line.authorize_access_token()
        userinfo = token.get('userinfo')
        # デバッグしたい場合は、トークン取得後にここにチェックを入れる
        # import pdb; pdb.set_trace()
        
    except Exception as e:
        error_msg = f"認証エラー: {str(e)}"
        current_app.logger.error(f"LINE Login Error: {error_msg}")
        userinfo = None

    if not userinfo or error_msg:
        flash(f'LINEログインに失敗しました。 {error_msg or ""}', 'danger')
        return redirect(url_for('auth.login'))

    line_id = userinfo.get('sub') # LINEのユーザー一意識別子
    
    # line_user_idが一致するユーザーを検索
    user = User.query.filter_by(line_user_id=line_id).first()
    
    if user:
        login_user(user, remember=True)
        flash(f"{user.name} としてログインしました（LINE連携）", "success")
        return redirect(url_for("auth.dashboard"))
    else:
        flash("このLINEアカウントは登録されていません。管理者にお問い合わせください。", "warning")
        return redirect(url_for('auth.login'))


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    # Summary counts
    stats = {
        "student_count": Student.query.count(),
        "staff_count": Staff.query.count(),
        "meeting_count": Meeting.query.count(),
    }
    
    latest_meetings = Meeting.query.order_by(Meeting.date.desc()).limit(3).all()
    start_date = datetime.now() - timedelta(weeks=8)

    # Fetch statistics using the helper
    student_data, staff_data = get_weekly_stats(start_date)

    # Consolidate weeks and map data
    all_weeks = sorted({r.week for r in student_data} | {r.week for r in staff_data})
    labels = [(w + timedelta(days=6)).strftime('%Y年%m月%d日') for w in all_weeks]
    student_map = {r.week: r.count for r in student_data}
    staff_map = {r.week: r.count for r in staff_data}
    
    students = Student.query.all()
    
    # 属性データの集計
    how_knew_counts = Counter([s.how_knew_class for s in students if s.how_knew_class])
    jlpt_counts = Counter([s.jlpt_level for s in students if s.jlpt_level])
    # Use .get() or handle None for residential area
    area_counts = Counter([
        s.residential_area if s.residential_area else "不明" 
        for s in students
    ])
    
    # 4. 出身国の集計
    country_counts = Counter([s.country_of_origin for s in students if s.country_of_origin])

    return render_template(
        "dashboard.html",
        **stats,
        latest_meetings=latest_meetings,
        labels=labels, 
        student_counts=[student_map.get(w, 0) for w in all_weeks],
        staff_counts=[staff_map.get(w, 0) for w in all_weeks],
        # --- 新規追加するグラフ用変数 ---
        how_knew_labels=list(how_knew_counts.keys()),
        how_knew_data=list(how_knew_counts.values()),
        jlpt_labels=list(jlpt_counts.keys()),
        jlpt_data=list(jlpt_counts.values()),
        area_labels=list(area_counts.keys()),
        area_data=list(area_counts.values()),
        country_labels=list(country_counts.keys()),
        country_data=list(country_counts.values())
    )


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()  # セッション破棄
    flash("ログアウトしました。", "info")
    return redirect(url_for("auth.login"))
