import os
from dotenv import load_dotenv

# .envファイルが存在する場合のみ読み込みます（ローカル環境用）
#
# Vercel環境ではファイルが存在しなくてもエラーにならず、無視されます
load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default-fallback-key")
    
    # データベースURLの取得
    # SQLAlchemy 1.4+ では 'postgres://' を受け付けないため、置換処理を入れるのが安全です
    DATABASE_URL = os.getenv("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL

    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")