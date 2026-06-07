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
    
    # # 簡易的な環境設定（本番環境では config.py などから読み込む）
    # if env_name == 'production':
    #     app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-production-secret-key')
    #     app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///school.db')
    # else:
    #     app.config['SECRET_KEY'] = 'dev-secret-key'
    #     app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dev_school.db'
        
    # app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # app/__init__.py 内の config 部分を修正
    if env_name == 'production':
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'placeholder-secret-key')
    
        # Vercel環境用のDB設定: 環境変数から取得。なければ一時的なメモリ内DB(sqlite:///:memory:)にしてエラーを防ぐ
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///:memory:')
    else:
        app.config['SECRET_KEY'] = 'dev-secret-key'
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dev_school.db'

    # 拡張機能の初期化
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
