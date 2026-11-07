import os
import base64
import hashlib
from datetime import date, datetime
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import TypeDecorator, String, Text

_fernet_instance = None
_cached_key_source = None


def get_fernet() -> Fernet:
    """
    Get or create a Fernet instance using STAFF_ENCRYPTION_KEY or SECRET_KEY.
    Derives a deterministic 32-byte URL-safe base64 key using SHA-256.
    """
    global _fernet_instance, _cached_key_source
    raw_key = (
        os.environ.get("STAFF_ENCRYPTION_KEY")
        or os.environ.get("SECRET_KEY")
        or "default-takesato-encryption-secret-key-salt"
    )
    if _fernet_instance is None or _cached_key_source != raw_key:
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        b64_key = base64.urlsafe_b64encode(digest)
        _fernet_instance = Fernet(b64_key)
        _cached_key_source = raw_key
    return _fernet_instance


def encrypt_value(value) -> str | None:
    """
    Encrypts a string value using Fernet. Returns None if value is None.
    If value is already empty string "", returns empty string "".
    """
    if value is None:
        return None
    str_val = str(value)
    if str_val == "":
        return ""
    try:
        fernet = get_fernet()
        return fernet.encrypt(str_val.encode("utf-8")).decode("utf-8")
    except Exception:
        return str_val


def decrypt_value(value) -> str | None:
    """
    Decrypts a Fernet ciphertext.
    If decryption fails (e.g. legacy plaintext stored in database),
    safely returns the original value so existing records never break.
    """
    if value is None:
        return None
    str_val = str(value)
    if str_val == "":
        return ""
    try:
        fernet = get_fernet()
        return fernet.decrypt(str_val.encode("utf-8")).decode("utf-8")
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
