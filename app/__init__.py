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
    
    if env_name == 'production':
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-production-secret-key')
        
        # Vercel上の環境変数 'DATABASE_URL' を読み込む
        # SQLAlchemyの仕様上、先頭が 'postgres://' の場合は 'postgresql://' に自動置換する安全策を入れます
        db_url = os.environ.get('DATABASE_URL')
        if db_url and db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
            
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    else:
        # ローカル開発環境（これまで通りSQLiteを使用）
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
