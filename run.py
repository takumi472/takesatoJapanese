import os
from app import create_app
from app import create_app, db
from app.models import User

# 環境変数 'FLASK_ENV' から設定を読み込む（デフォルトは 'development'）
env = os.environ.get('FLASK_ENV', 'development')
app = create_app(env)

if __name__ == '__main__':
    # 開発環境の場合はデバッグモードを有効にし、ホットリロード（自動再起動）を有効化
    is_debug = (env == 'development')
    
    with app.app_context():
        db.create_all() # テーブルがなければ作成
    
        # テスト用アドミンユーザーがいなければ作成
        if not User.query.filter_by(username='admin@example.com').first():
            admin = User(username='admin@example.com', role='admin', name='管理者 太郎')
            admin.set_password('password123') # パスワードをハッシュ化
            db.session.add(admin)
            db.session.commit()
    
    # アプリケーションの起動
    # 外部ホスト（スマホなど）からアクセスさせたい場合は host='0.0.0.0' に変更してください
    app.run(
        host='127.0.0.1', 
        port=5000, 
        debug=is_debug
    )