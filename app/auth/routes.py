import os
from flask import (
    Blueprint,
    make_response,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)
import requests
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from urllib.parse import urlparse
from datetime import datetime, timedelta
from app import db
from app.models import User, Student, Staff, Meeting, LearningRecord
from collections import Counter
import secrets
import smtplib
import ssl
from authlib.integrations.flask_client import OAuth

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()

# LINEの設定（エラーを回避するため、エンドポイントを明示的に指定）

# LINEの設定
line = oauth.register(
    name="line",
    client_id=os.environ.get("LINE_CLIENT_ID"),
    client_secret=os.environ.get("LINE_CLIENT_SECRET"),
    server_metadata_url="https://access.line.me/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid profile email",
        "token_endpoint_auth_method": "client_secret_post",
    },
)
# line = oauth.register(
#     name="line",
#     client_id=os.environ.get("LINE_CLIENT_ID"),
#     client_secret=os.environ.get("LINE_CLIENT_SECRET"),
#     server_metadata_url="https://access.line.me/.well-known/openid-configuration",
#     client_kwargs={
#         "scope": "openid profile email",
#         "token_endpoint_auth_method": "client_secret_post",
#         # 🔑 Force Authlib to recognize and accept the RS256 algorithm signature
#         "id_token_signed_response_alg": None,
#     },
# )
# line = oauth.register(
#     name="line",
#     client_id=os.environ.get("LINE_CLIENT_ID"),
#     client_secret=os.environ.get("LINE_CLIENT_SECRET"),
#     server_metadata_url="https://access.line.me/.well-known/openid-configuration",
#     client_kwargs={
#         "scope": "openid profile email",
#         "token_endpoint_auth_method": "client_secret_post",
#     },
# )
# line = oauth.register(
#     name="line",
#     client_id=os.environ.get("LINE_CLIENT_ID"),
#     client_secret=os.environ.get("LINE_CLIENT_SECRET"),
#     api_base_url="https://api.line.me/v2/",
#     authorize_url="https://access.line.me/oauth2/v2.1/authorize",
#     access_token_url="https://api.line.me/oauth2/v2.1/token",
#     # jwks_uri="https://api.line.me/oauth2/v2.1/certs",
#     client_kwargs={
#         "scope": "openid profile email",
#         # 内部でのJWT検証（JWS）の手続きを強制的にオフにする
#         "token_endpoint_auth_method": "client_secret_post",
#         # LINEのIDトークンは通常RS256ですが、環境に応じて自動検証させるため
#         # 必要に応じて 'HS256' に戻せるよう、指定を柔軟にするかデフォルトに委ねます
#     },
# )


def get_weekly_stats(start_date):
    """Helper to fetch weekly unique counts for students and staff."""
    # Note: date_trunc is PostgreSQL specific.
    student_query = (
        db.session.query(
            func.date_trunc("week", LearningRecord.lesson_date).label("week"),
            func.count(LearningRecord.student_id.distinct()).label("count"),
        )
        .filter(LearningRecord.lesson_date >= start_date)
        .group_by("week")
    )

    staff_query = (
        db.session.query(
            func.date_trunc("week", LearningRecord.lesson_date).label("week"),
            func.count(LearningRecord.staff_id.distinct()).label("count"),
        )
        .filter(LearningRecord.lesson_date >= start_date)
        .group_by("week")
    )

    return student_query.all(), staff_query.all()


@auth_bp.record_once
def on_load(state):
    oauth.init_app(state.app)


@auth_bp.route("/", methods=["GET", "POST"])
def auth_route():
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # 既にログイン済みの場合は、ダッシュボードへリダイレクト
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
            if not next_page or urlparse(next_page).netloc != "":
                next_page = url_for("auth.dashboard")
            return redirect(next_page)
        else:
            flash("ユーザー名またはパスワードが正しくありません。", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/login/line")
def login_line():
    """LINEの認証画面へリダイレクト"""
    redirect_uri = url_for("auth.line_callback", _external=True)
    return line.authorize_redirect(redirect_uri)


@auth_bp.route("/login/line/callback")
def line_callback():
    """LINEから戻ってきた後の処理"""
    current_app.logger.info("=== LINE Login Callback Started ===")

    # 1. URLパラメータから 'code' と 'state' を直接取得
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    current_app.logger.info(
        f"Received query parameters - code: {'Present' if code else 'Missing'}, state: {state}, error: {error}"
    )

    if error:
        current_app.logger.error(f"LINE Login Error Parameter from URL: {error}")
        flash(f"LINEログインに失敗しました。 {error}", "danger")
        return redirect(url_for("auth.login"))

    if not code:
        current_app.logger.error(
            "LINE Login Error: Missing 'code' parameter in redirect URI."
        )
        flash("認証コードが取得できませんでした。", "danger")
        return redirect(url_for("auth.login"))

    userinfo = None
    try:
        # 2. Authlibを完全にバイパスし、LINEのトークンエンドポイントへ直接POSTリクエストを送る
        token_url = "https://api.line.me/oauth2/v2.1/token"
        redirect_uri = url_for("auth.line_callback", _external=True)

        current_app.logger.info(
            f"Exchanging code for token. Redirect URI used: {redirect_uri}"
        )

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": os.environ.get("LINE_CLIENT_ID"),
            "client_secret": os.environ.get("LINE_CLIENT_SECRET"),
        }

        token_response = requests.post(token_url, headers=headers, data=data)
        current_app.logger.info(
            f"Token API Response Status Code: {token_response.status_code}"
        )

        if token_response.status_code != 200:
            raise Exception(f"トークン交換に失敗しました: {token_response.text}")

        token_data = token_response.json()
        id_token = token_data.get("id_token")

        if not id_token:
            raise Exception("応答にIDトークンが含まれていません。")

        current_app.logger.info("Successfully received id_token from LINE.")

        # 3. LINEの公式検証エンドポイントを使って安全にユーザーデータをデコード
        verify_url = "https://api.line.me/oauth2/v2.1/verify"
        verify_data = {
            "id_token": id_token,
            "client_id": os.environ.get("LINE_CLIENT_ID"),
        }

        current_app.logger.info("Sending id_token to LINE verification endpoint...")
        verify_response = requests.post(verify_url, data=verify_data)
        current_app.logger.info(
            f"Verification API Response Status Code: {verify_response.status_code}"
        )

        if verify_response.status_code != 200:
            raise Exception(
                f"LINEサーバーによるトークン検証エラー: {verify_response.text}"
            )

        userinfo = verify_response.json()
        current_app.logger.info("LINE id_token verification successful.")

    except Exception as e:
        current_app.logger.error(f"LINE Login Exception during token flow: {str(e)}")
        flash(f"認証エラーが発生しました。{str(e)}", "danger")
        return redirect(url_for("auth.login"))

    # 4. ユーザー識別子 (sub) のチェック
    current_app.logger.info(f"LINE USER PROFILE : {userinfo}")
    line_id = userinfo.get("sub")
    line_name = userinfo.get("name")

    current_app.logger.info(
        f"Extracted LINE user profile - sub (ID): {line_id}, name: {line_name}"
    )

    if not line_name:
        current_app.logger.error(
            "LINE Login Error: 'sub' (User ID) field missing from verified userinfo response."
        )
        flash("LINEからユーザー識別子を取得できませんでした。", "danger")
        return redirect(url_for("auth.login"))

    # 5. データベース照合処理
    current_app.logger.info(
        f"Searching database for local user matched with line_user_id: {line_id}"
    )
    user = User.query.filter_by(line_user_id=line_name).first()

    if user:
        current_app.logger.info(
            f"Match found in DB. Local User ID: {user.id}, Username: {user.username}"
        )
        login_user(user, remember=True)

        display_name = getattr(user, "name", None) or getattr(
            user, "username", "ユーザー"
        )
        flash(f"{display_name} としてログインしました（LINE連携）", "success")

        current_app.logger.info(
            f"User {user.username} successfully authenticated via LINE. Redirecting to dashboard."
        )
        return redirect(url_for("auth.dashboard"))
    else:
        current_app.annotate_logging = True  # Optional indicator
        current_app.logger.warning(
            f"LINE Login Warning: No DB record found mapping to line_user_id '{line_id}' (LINE Name: {line_name})."
        )
        flash(
            "このLINEアカウントはシステムに登録されていません。管理者にお問い合わせください。",
            "warning",
        )
        return redirect(url_for("auth.login"))


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
    labels = [(w + timedelta(days=6)).strftime("%Y年%m月%d日") for w in all_weeks]
    student_map = {r.week: r.count for r in student_data}
    staff_map = {r.week: r.count for r in staff_data}

    # --- パフォーマンス改善: DB側で集計 ---
    # 以前の実装: students = Student.query.all() で全件取得してからPythonでループ処理
    # 改善後: DBのgroup_byとcountを使い、必要な集計結果のみを取得
    def get_counts(column):
        """指定されたカラムの非NULL値の数をグループ化して取得するヘルパー関数"""
        return (
            db.session.query(column, func.count(column))
            .filter(column.isnot(None))
            .group_by(column)
            .all()
        )

    # 属性データの集計
    how_knew_counts = dict(get_counts(Student.how_knew_class))
    jlpt_counts = dict(get_counts(Student.jlpt_level))
    country_counts = dict(get_counts(Student.country_of_origin))

    # 居住地はNULLの場合 '不明' として扱いたいので、個別に処理
    area_results = (
        db.session.query(
            func.coalesce(Student.residential_area, "不明"),
            func.count(Student.id),
        )
        .group_by(func.coalesce(Student.residential_area, "不明"))
        .all()
    )
    area_counts = dict(area_results)

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
        country_data=list(country_counts.values()),
    )


@auth_bp.route("/manual")
@login_required
def manual():
    """Display the application manual page."""
    return render_template("manual.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()  # セッション破棄
    flash("ログアウトしました。", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        # 管理者でなければ操作不可

        username = request.form.get("username")
        new_password = request.form.get("new_password")

        user = User.query.filter_by(username=username).first()

        if not user:
            flash("入力されたユーザー名は登録されていません。", "warning")
            return redirect(url_for("auth.forgot_password"))

        try:
            user.set_password(new_password)
            db.session.commit()
            flash(f"{user.name}さんのパスワードを正常にリセットしました。", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error resetting password for {username}: {e}")
            flash("パスワードのリセット中にエラーが発生しました。", "danger")

    return render_template("auth/forgot_password.html")
