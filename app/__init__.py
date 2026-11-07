# app/__init__.py
import os
import mimetypes
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import cloudinary
from dotenv import load_dotenv  # .envファイルをロードするために追加
import cloudinary.uploader
from datetime import timedelta
from werkzeug.middleware.proxy_fix import ProxyFix

# 動画などのMIMEタイプを確実に登録（コンテナ環境対策）
mimetypes.add_type("video/mp4", ".mp4")

db = SQLAlchemy()
login_manager = LoginManager()


def create_app(env_name="development"):
    load_dotenv()  # アプリケーション起動時に.envファイルをロード
    basedir = os.path.abspath(os.path.dirname(__file__))

    app = Flask(__name__, static_folder=os.path.join(basedir, "static"))
    is_production = not (
        env_name == "development" or os.environ.get("FLASK_ENV") == "development"
    )

    # 共通のシークレットキー設定（本番環境での安全なキー保証）
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key or secret_key in (
        "dev-key-placeholder",
        "your-flask-secret-key-here",
    ):
        if is_production:
            import secrets

            secret_key = secrets.token_hex(32)
            app.logger.warning(
                "Warning: 本番環境でSECRET_KEYが未設定またはデフォルトのため、安全なランダムキーを生成しました。"
            )
        else:
            secret_key = "dev-key-placeholder"
    app.config["SECRET_KEY"] = secret_key
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Cloud Run 等の本番コンテナ環境向け静的ファイル配信 (WhiteNoise)
    try:
        from whitenoise import WhiteNoise

        static_dir = os.path.join(basedir, "static")
        app.wsgi_app = WhiteNoise(app.wsgi_app, root=static_dir, prefix="static/")
    except ImportError:
        pass

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

    # セキュリティ強化: Cookie設定 (CSRF・セッションハイジャック対策)
    app.config.update(
        REMEMBER_COOKIE_DURATION=timedelta(days=3650),  # 10年間保持
        PERMANENT_SESSION_LIFETIME=timedelta(days=3650),  # セッション保持
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_production,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=is_production,
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # リクエスト最大16MB制限 (DoS対策)
    )

    # セキュリティヘッダーの自動付与 (クリックジャッキング・MIMEスニッフィング・XSS対策)
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    trusted_origins_env = os.environ.get("CSRF_TRUSTED_ORIGINS")
    if trusted_origins_env:
        app.config["WTF_CSRF_TRUSTED_ORIGINS"] = [
            origin.strip() for origin in trusted_origins_env.split(",")
        ]
    else:
        app.config["WTF_CSRF_TRUSTED_ORIGINS"] = [
            "https://www.takesato-japanese.net",
            "http://www.takesato-japanese.net",
        ]

    # CSRF保護（Origin / Referer検証によるクロスサイトPOST攻撃遮断）
    from app.csrf import init_csrf_protection

    init_csrf_protection(app)
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
            from app.models import TextbookOrder  # モデル読み込み

            db.create_all()  # 未作成テーブル（textbook_orders等）の自動生成

            if db.engine.dialect.name == "sqlite":
                res = db.session.execute(text("PRAGMA table_info(students);")).fetchall()
                col_names = [r[1] for r in res]
                if col_names and "display_order" not in col_names:
                    db.session.execute(
                        text("ALTER TABLE students ADD COLUMN display_order INTEGER DEFAULT 0;")
                    )
                    db.session.commit()

                # textbook_orders テーブルの新カラム追加
                res_tb = db.session.execute(text("PRAGMA table_info(textbook_orders);")).fetchall()
                tb_col_names = [r[1] for r in res_tb]
                new_tb_cols = [
                    "hajimete_kanji_4", "hajimete_kanji_5",
                    "nihongo_yomimono_shokyu_1", "nihongo_yomimono_chukyu_1",
                    "nihongo_yomimono_chukyu_2", "hiragana_katakana_sheet"
                ]
                for col in new_tb_cols:
                    if tb_col_names and col not in tb_col_names:
                        db.session.execute(text(f"ALTER TABLE textbook_orders ADD COLUMN {col} INTEGER DEFAULT 0;"))
                        db.session.commit()
            elif db.engine.dialect.name == "postgresql":
                db.session.execute(
                    text("ALTER TABLE students ADD COLUMN IF NOT EXISTS display_order INTEGER DEFAULT 0;")
                )
                db.session.commit()

                # textbook_orders テーブルの新カラム追加
                new_tb_cols = [
                    "hajimete_kanji_4", "hajimete_kanji_5",
                    "nihongo_yomimono_shokyu_1", "nihongo_yomimono_chukyu_1",
                    "nihongo_yomimono_chukyu_2", "hiragana_katakana_sheet"
                ]
                for col in new_tb_cols:
                    try:
                        db.session.execute(text(f"ALTER TABLE textbook_orders ADD COLUMN IF NOT EXISTS {col} INTEGER DEFAULT 0;"))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

                # スタッフテーブルの暗号化用カラム型拡張
                staff_alter_queries = [
                    "ALTER TABLE staffs ALTER COLUMN email TYPE VARCHAR(512);",
                    "ALTER TABLE staffs ALTER COLUMN submission_date TYPE VARCHAR(512) USING submission_date::text;",
                    "ALTER TABLE staffs ALTER COLUMN last_name_kanji TYPE VARCHAR(512);",
                    "ALTER TABLE staffs ALTER COLUMN first_name_kanji TYPE VARCHAR(512);",
                    "ALTER TABLE staffs ALTER COLUMN last_name_kana TYPE VARCHAR(512);",
                    "ALTER TABLE staffs ALTER COLUMN first_name_kana TYPE VARCHAR(512);",
                    "ALTER TABLE staffs ALTER COLUMN post_code TYPE VARCHAR(512);",
                    "ALTER TABLE staffs ALTER COLUMN address TYPE TEXT;",
                    "ALTER TABLE staffs ALTER COLUMN tel_main TYPE VARCHAR(512);",
                    "ALTER TABLE staffs ALTER COLUMN tel_sub TYPE VARCHAR(512);",
                ]
                for q in staff_alter_queries:
                    try:
                        db.session.execute(text(q))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

            # 既存の平文スタッフレコードがあれば自動暗号化
            from app.crypto import migrate_existing_staff_records
            migrate_existing_staff_records(db.session)
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"Auto-migration notice: {e}")

    # --- Blueprintの登録などはこの下に記述 ---
    from app.auth.routes import auth_bp
    from app.staff.routes import staff_bp
    from app.student.routes import student_bp
    from app.record.routes import record_bp
    from app.meeting.routes import meeting_bp
    from app.textbook.routes import textbook_bp

    app.register_blueprint(auth_bp, url_prefix="/")
    app.register_blueprint(staff_bp, url_prefix="/staff")
    app.register_blueprint(student_bp, url_prefix="/student")
    app.register_blueprint(record_bp, url_prefix="/record")
    app.register_blueprint(meeting_bp, url_prefix="/meeting")
    app.register_blueprint(textbook_bp, url_prefix="/textbook")

    return app
