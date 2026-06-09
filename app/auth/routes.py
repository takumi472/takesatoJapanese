# app/auth/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import Interval, cast, func
from datetime import datetime, timedelta
from app import db
from app.models import User, Student, Staff, Meeting, LearningRecord

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
    # Summary counts
    stats = {
        "student_count": Student.query.count(),
        "staff_count": Staff.query.count(),
        "meeting_count": Meeting.query.count(),
    }
    
    latest_meetings = Meeting.query.order_by(Meeting.date.desc()).limit(3).all()
    start_date = datetime.now() - timedelta(weeks=8)

    # Helper to fetch weekly unique counts for a specific column
    def get_weekly_counts(column):
        return db.session.query(
            func.date_trunc('week', LearningRecord.lesson_date).label('week'),
            func.count(column.distinct()).label('count')
        ).filter(LearningRecord.lesson_date >= start_date)\
         .group_by('week').order_by('week').all()

    student_data = get_weekly_counts(LearningRecord.student_id)
    staff_data = get_weekly_counts(LearningRecord.staff_id)

    # Consolidate weeks and map data
    all_weeks = sorted({r.week for r in student_data} | {r.week for r in staff_data})
    labels = [(w + timedelta(days=6)).strftime('%Y年%m月%d日') for w in all_weeks]
    student_map = {r.week: r.count for r in student_data}
    staff_map = {r.week: r.count for r in staff_data}

    return render_template(
        "dashboard.html",
        **stats,
        latest_meetings=latest_meetings,
        labels=labels, 
        student_counts=[student_map.get(w, 0) for w in all_weeks],
        staff_counts=[staff_map.get(w, 0) for w in all_weeks]
    )


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()  # セッション破棄
    flash("ログアウトしました。", "info")
    return redirect(url_for("auth.login"))
