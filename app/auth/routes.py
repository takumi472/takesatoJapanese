# app/auth/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app.models import Student, Staff

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

    # もし議事録モデルがある場合はカウント（なければ固定文字列等で対応可能）
    # meeting_count = MeetingMinutes.query.count()

    return render_template(
        "dashboard.html",
        student_count=student_count,
        staff_count=staff_count,
        # meeting_count=meeting_count
    )


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()  # セッション破棄
    flash("ログアウトしました。", "info")
    return redirect(url_for("auth.login"))
