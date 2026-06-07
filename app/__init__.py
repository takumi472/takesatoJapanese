# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os

# 拡張機能のインスタンス化
db = SQLAlchemy()
login_manager = LoginManager()

def create_app(env_name='development'):
    app = Flask(__name__)
    
    if env_name == 'production' or os.environ.get('VERCEL'):
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-prod-key')
        
        # 1. Vercelの環境変数からURLを取得
        raw_db_url = os.environ.get('DATABASE_URL')
        
        if raw_db_url:
            # 2. 【PostgreSQL最適化①】postgres:// を postgresql:// に厳密に置換
            if raw_db_url.startswith("postgres://"):
                raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
            
            # 3. 【PostgreSQL最適化②】SSL接続とパブリックススキーマの明示
            # URLにまだクエリパラメータがついていない場合は、安全に付与する
            if "?" not in raw_db_url:
                raw_db_url += "?sslmode=require&options=-c%20search_path%3Dpublic"
            elif "search_path" not in raw_db_url:
                raw_db_url += "&options=-c%20search_path%3Dpublic"
                
            app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
        else:
            # 万が一URLが空だった場合のフォールバック
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
            
        # 4. 【PostgreSQL最適化③】接続のタイムアウトやプール管理の追加
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            "pool_pre_ping": True, # 接続が切れていないか毎回チェックする安全弁
            "pool_recycle": 300,
        }
        
    else:
        # ローカル開発環境（SQLite）
        app.config['SECRET_KEY'] = 'dev-secret-key'
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dev_school.db'
        
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login' # 未ログイン時のリダイレクト先

    # Blueprint（ブループリント）の登録
    from app.auth.routes import auth_bp
    from app.staff.routes import staff_bp
    from app.student.routes import student_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(staff_bp, url_prefix='/staff')
    app.register_blueprint(student_bp, url_prefix='/student')

    return app
