# app/limiter.py
"""
DDoS・ブルートフォース攻撃防止のためのレートリミッター
Flask-Limiter が存在する場合は有効化し、未インストールの場合は透過的に動作します。
"""
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["300 per minute", "60 per second"],
        storage_uri="memory://",
    )
except ImportError:
    class DummyLimiter:
        def limit(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator

        def init_app(self, app):
            pass

    limiter = DummyLimiter()

