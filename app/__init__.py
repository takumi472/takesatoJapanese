# app/__init__.py
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import cloudinary
from dotenv import load_dotenv  # .envファイルをロードするために追加
import cloudinary.uploader
from datetime import timedelta
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
login_manager = LoginManager()


def create_app(env_name="development"):
    load_dotenv()  # アプリケーション起動時に.envファイルをロード

    app = Flask(__name__, static_folder="app/static", static_url_path="/static")

    # 共通のシークレットキー設定
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-placeholder")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # 1. Vercel(本番)でもローカル(開発)でも、環境変数からDATABASE_URLを取得する
    raw_db_url = os.environ.get("DATABASE_URL")

    if raw_db_url:
        # 2. postgres:// を postgresql:// に変換（SQLAlchemyの必須対策）
        raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

        app.config["SQLALCHEMY_DATABASE_URI"] = raw_db_url
    else:
        # 万が一接続URLがどこにもない場合の安全弁
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///dev_school.db"
        print(
            "Warning: DATABASE_URL が設定されていないため、一時的にSQLiteを使用します。"
        )

    # 3. 接続プール・タイムアウトの設定
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    app.config.update(
        REMEMBER_COOKIE_DURATION=timedelta(days=3650),  # 10年間保持
        PERMANENT_SESSION_LIFETIME=timedelta(days=3650),  # セッションも長くする
    )
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
        secure=True,
    )

    # 各種マネージャーの初期化
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    db.init_app(app)

    with app.app_context():
        try:
            from sqlalchemy import text

            if db.engine.dialect.name == "sqlite":
                res = db.session.execute(text("PRAGMA table_info(students);")).fetchall()
                col_names = [r[1] for r in res]
                if col_names and "display_order" not in col_names:
                    db.session.execute(
                        text("ALTER TABLE students ADD COLUMN display_order INTEGER DEFAULT 0;")
                    )
                    db.session.commit()
            elif db.engine.dialect.name == "postgresql":
                db.session.execute(
                    text("ALTER TABLE students ADD COLUMN IF NOT EXISTS display_order INTEGER DEFAULT 0;")
                )
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"Auto-migration notice: {e}")

    # --- Blueprintの登録などはこの下に記述 ---
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
