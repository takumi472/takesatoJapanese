# app/decorators.py
from functools import wraps
from flask import abort
from flask_login import current_user

def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403) # 権限なし（Forbidden）
            return f(*args, **kwargs)
        return decorated_view
    return decorator