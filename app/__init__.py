# app/__init__.py の該当箇所
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

def create_app(env_name='development'):
    app = Flask(__name__)
    
    if env_name == 'production' or os.environ.get('VERCEL'):
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-prod-key')
        
        # 1. Vercelの環境変数からURLを取得
        raw_db_url = os.environ.get('DATABASE_URL')
        
        if raw_db_url:
            # 2. 【重要】postgres:// を postgresql:// に直す処理だけを行う
            # エラーの原因になっていた "options=-c search_path..." の追加処理は完全に削除します
            if raw_db_url.startswith("postgres://"):
                raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
                
            app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
        else:
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
            
        # 3. サーバーレス環境向けの接続プール最適化
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            "pool_pre_ping": True,
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
