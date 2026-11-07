import os
import base64
import hashlib
from datetime import date, datetime
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from sqlalchemy.types import TypeDecorator, String, Text

_multi_fernet_instance = None
_cached_keys_tuple = None


def _derive_fernet_key(raw_str: str) -> bytes:
    """文字列からSHA-256を用いて32バイトのURLセーフBase64キーを導出"""
    digest = hashlib.sha256(raw_str.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_multi_fernet() -> MultiFernet:
    """
    ローカルとCloud Runなど異なる環境間で鍵の不一致が起きても確実に復号できるよう、
    複数の暗号化キーをサポートする MultiFernet インスタンスを取得します。
    1. STAFF_ENCRYPTION_KEY（明示的な環境変数・最優先）
    2. SECRET_KEY（Flask環境変数）
    3. ローカル開発環境キー ("your-flask-secret-key-here")
    4. デフォルトフォールバック ("default-takesato-encryption-secret-key-salt")
    """
    global _multi_fernet_instance, _cached_keys_tuple

    candidates = []

    # 1. 専用の暗号化キー環境変数
    env_staff = os.environ.get("STAFF_ENCRYPTION_KEY")
    if env_staff:
        candidates.append(env_staff.strip())

    # 2. FlaskのSECRET_KEY環境変数
    env_secret = os.environ.get("SECRET_KEY")
    if env_secret:
        candidates.append(env_secret.strip())

    # 3. ローカル開発環境（.env）で過去・現在使われた既知のキー
    candidates.append("your-flask-secret-key-here")
    candidates.append("dev-key-placeholder")

    # 4. デフォルトのフォールバックソルト
    candidates.append("default-takesato-encryption-secret-key-salt")

    # 重複を排除し順序を維持
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    current_tuple = tuple(unique_candidates)
    if _multi_fernet_instance is None or _cached_keys_tuple != current_tuple:
        fernets = [Fernet(_derive_fernet_key(k)) for k in unique_candidates]
        _multi_fernet_instance = MultiFernet(fernets)
        _cached_keys_tuple = current_tuple

    return _multi_fernet_instance


def get_fernet():
    """下位互換性のためのエイリアス"""
    return get_multi_fernet()


def encrypt_value(value) -> str | None:
    """
    MultiFernetの先頭キー（最優先キー）を使用して文字列を暗号化します。
    """
    if value is None:
        return None
    str_val = str(value)
    if str_val == "":
        return ""
    try:
        mf = get_multi_fernet()
        return mf.encrypt(str_val.encode("utf-8")).decode("utf-8")
    except Exception:
        return str_val


def decrypt_value(value) -> str | None:
    """
    MultiFernetに登録された全キーを順に試して文字列を復号します。
    ローカル環境で暗号化されたデータもCloud Runで確実に復号できます。
    万が一平文や破損データの場合は安全に元の値を返します。
    """
    if value is None:
        return None
    str_val = str(value)
    if str_val == "":
        return ""
    try:
        mf = get_multi_fernet()
        return mf.decrypt(str_val.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # Graceful fallback for legacy plaintext data
        return str_val


class EncryptedString(TypeDecorator):
    """
    SQLAlchemy TypeDecorator that encrypts strings before saving to database
    and decrypts them on retrieval.
    """
    impl = String
    cache_ok = True

    def __init__(self, length=512, *args, **kwargs):
        super().__init__(length=length, *args, **kwargs)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_value(value)


class EncryptedText(TypeDecorator):
    """
    SQLAlchemy TypeDecorator for longer text fields (TEXT type).
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_value(value)


class EncryptedDate(TypeDecorator):
    """
    SQLAlchemy TypeDecorator that encrypts dates as ISO strings (YYYY-MM-DD),
    storing them as String(512), and returning datetime.date on retrieval.
    """
    impl = String(512)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (date, datetime)):
            iso_str = value.strftime("%Y-%m-%d")
        else:
            iso_str = str(value).strip()
        if not iso_str:
            return None
        return encrypt_value(iso_str)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        decrypted = decrypt_value(value)
        if not decrypted:
            return None
        try:
            return datetime.strptime(decrypted.strip(), "%Y-%m-%d").date()
        except Exception:
            try:
                return datetime.fromisoformat(decrypted.strip()).date()
            except Exception:
                return None


def migrate_existing_staff_records(session):
    """
    Scans the staffs table for any legacy plaintext records and encrypts them.
    Safe to run repeatedly; skips already-encrypted records.
    """
    from sqlalchemy import text
    try:
        rows = session.execute(
            text(
                "SELECT id, email, submission_date, last_name_kanji, first_name_kanji, "
                "last_name_kana, first_name_kana, post_code, address, tel_main, tel_sub "
                "FROM staffs"
            )
        ).fetchall()

        for row in rows:
            staff_id = row[0]
            updates = {}
            col_names = [
                "email", "submission_date", "last_name_kanji", "first_name_kanji",
                "last_name_kana", "first_name_kana", "post_code", "address",
                "tel_main", "tel_sub"
            ]
            for i, col in enumerate(col_names, start=1):
                val = row[i]
                if val is not None:
                    str_val = str(val).strip()
                    if str_val and not (str_val.startswith("gAAAAA") and len(str_val) >= 90):
                        updates[col] = encrypt_value(str_val)

            if updates:
                set_clauses = [f"{k} = :{k}" for k in updates.keys()]
                sql = f"UPDATE staffs SET {', '.join(set_clauses)} WHERE id = :id"
                params = dict(updates)
                params["id"] = staff_id
                session.execute(text(sql), params)

        session.commit()
    except Exception:
        session.rollback()
