# app/auth/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app.models import Student, Staff, Meeting
from sqlalchemy import Interval, cast, func
from datetime import datetime, timedelta
from app.models import LearningRecord
from app import db 
from sqlalchemy import func
from app.models import LearningRecord

auth_bp = Blueprint("auth", __name__)


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
            login_user(user)  # セッション開始

            # 次にアクセスしようとしていたURL（あれば）を取得、なければ生徒一覧へ
            next_page = request.args.get("next")
            return redirect(next_page) if next_page else redirect(url_for("auth.dashboard"))
        else:
            # エラーメッセージをフロントに通知
            flash("ユーザー名またはパスワードが正しくありません。", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    student_count = Student.query.count()
    staff_count = Staff.query.count()
    meeting_count = Meeting.query.count()
    latest_meetings = Meeting.query.order_by(Meeting.date.desc()).limit(3).all() or []
    start_date = datetime.now() - timedelta(weeks=8)
    student_data = db.session.query(
        func.date_trunc('week', LearningRecord.lesson_date).label('week'),
        func.count(LearningRecord.student_id.distinct()).label('count')  # ここを修正
    ).filter(LearningRecord.lesson_date >= start_date)\
     .group_by('week').order_by('week').all()

    # 2. スタッフの参加人数（重複を除外してユニークなスタッフ数をカウント）
    # ※もしMeetingが「開催されたミーティングの総数」なら distinct は不要ですが、
    # 「参加したスタッフの重複を除いた人数」にしたい場合は以下のようにします。
    staff_data = db.session.query(
        func.date_trunc('week', LearningRecord.lesson_date).label('week'),
        func.count(LearningRecord.staff_id.distinct()).label('count')  # ここを修正
    ).filter(LearningRecord.lesson_date >= start_date)\
     .group_by('week').order_by('week').all()

    # 辞書に変換してマッピング（週をキーにして集計）
    weeks = sorted(list(set([r.week for r in student_data] + [r.week for r in staff_data])))
    weekly_counts = db.session.query(
        # 月曜日（date_trunc）に6日を足して日曜日にする
        func.to_char(func.date_trunc('week', LearningRecord.lesson_date) + cast('6 days', Interval), 'YYYY年MM月DD日').label('week'),
        func.count(LearningRecord.id).label('count')
    ) .filter(LearningRecord.lesson_date >= start_date)\
    .group_by(func.date_trunc('week', LearningRecord.lesson_date))\
    .order_by(func.date_trunc('week', LearningRecord.lesson_date)).all()
    # python側での加工例
    labels = [f"{(w + timedelta(days=6)).strftime('%Y年%m月%d日')}" for w in weeks]
    
    student_map = {r.week: r.count for r in student_data}
    staff_map = {r.week: r.count for r in staff_data}

    # もし議事録モデルがある場合はカウント（なければ固定文字列等で対応可能）
    # meeting_count = MeetingMinutes.query.count()

    return render_template(
        "dashboard.html",
        student_count=student_count,
        staff_count=staff_count,
        meeting_count=meeting_count,
        latest_meetings=latest_meetings,
        labels=labels, 
        student_counts=[student_map.get(w, 0) for w in weeks],
        staff_counts=[staff_map.get(w, 0) for w in weeks]
    )


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()  # セッション破棄
    flash("ログアウトしました。", "info")
    return redirect(url_for("auth.login"))
