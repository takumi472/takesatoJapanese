from urllib.parse import urlparse
from flask import request, abort, current_app, session
import secrets


def get_csrf_token():
    """セッション固有の暗号学的に安全なCSRFトークンを取得・生成"""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def init_csrf_protection(app):
    """
    堅牢な多層CSRF保護をアプリケーションに設定:
    1. Origin / Referer ヘッダーの Same-Origin 検証（全POST/PUT/PATCH/DELETEに対する防御）
    2. Jinja2テンプレート用 csrf_token() の提供
    3. クライアントサイドAPI用ヘッダー検証対応
    """
    app.jinja_env.globals["csrf_token"] = get_csrf_token

    @app.before_request
    def verify_same_origin_csrf():
        # 安全なHTTP読み取りメソッドは検証をスキップ
        if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            return None

        # LINEログイン等の外部OAuthコールバック・特定除外パス
        exempt_prefixes = [
            "/login/line/callback",
        ]
        for prefix in exempt_prefixes:
            if request.path.startswith(prefix):
                return None

        # 1. Origin ヘッダーの検証（モダンブラウザがPOST送信時に必ず付与）
        origin = request.headers.get("Origin")
        if origin:
            origin_host = urlparse(origin).netloc
            if origin_host and origin_host != request.host:
                current_app.logger.warning(
                    f"CSRF Blocked: Origin mismatch. Origin: {origin_host}, Host: {request.host}, Path: {request.path}"
                )
                abort(403, description="クロスサイトリクエストが検出されたため拒否されました (CSRF Protection)。")
            return None

        # 2. Referer ヘッダーの検証（Originが無い場合のフォールバック）
        referer = request.headers.get("Referer")
        if referer:
            referer_host = urlparse(referer).netloc
            if referer_host and referer_host != request.host:
                current_app.logger.warning(
                    f"CSRF Blocked: Referer mismatch. Referer: {referer_host}, Host: {request.host}, Path: {request.path}"
                )
                abort(403, description="クロスサイトリクエストが検出されたため拒否されました (CSRF Protection)。")
            return None

        return None
