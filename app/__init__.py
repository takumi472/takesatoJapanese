# app/__init__.py
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()


def create_app(env_name="development"):
    app = Flask(__name__)

    # 共通のシークレットキー設定
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-placeholder")

    # 1. Vercel(本番)でもローカル(開発)でも、環境変数からDATABASE_URLを取得する
    raw_db_url = os.environ.get("DATABASE_URL")

    # 【ローカル開発用のフォールバック設定】
    # もしローカル環境で環境変数を設定するのが面倒な場合は、
    # 以下の '' の中に Neon の postgres://... のURLを直接貼り付けておくと確実です。
    if env_name == "development" and not raw_db_url:
        raw_db_url = "ここにNeonでコピーした接続URLを貼り付ける"

    if raw_db_url:
        # 2. postgres:// を postgresql:// に変換（SQLAlchemyの必須対策）
        if raw_db_url.startswith("postgres://"):
            raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

        app.config["SQLALCHEMY_DATABASE_URI"] = raw_db_url
    else:
        # 万が一接続URLがどこにもない場合の安全弁
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///dev_school.db"
        print("Warning: DATABASE_URL が設定されていないため、一時的にSQLiteを使用します。")

    # 3. 接続プール・タイムアウトの設定
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # 各種マネージャーの初期化
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    db.init_app(app)

    # --- Blueprintの登録などはこの下に記述 ---i
    from app.auth.routes import auth_bp
    from app.staff.routes import staff_bp
    from app.student.routes import student_bp
    from app.record.routes import record_bp
    from app.meeting.routes import meeting_bp

    app.register_blueprint(auth_bp, url_prefix="/")
    app.register_blueprint(staff_bp, url_prefix="/staff")
    app.register_blueprint(student_bp, url_prefix="/student")
    app.register_blueprint(record_bp, url_prefix="/record")
    app.register_blueprint(meeting_bp, url_prefix="/meeting")

    return app
