from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy.sql import expression
from app.crypto import EncryptedString, EncryptedText, EncryptedDate

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    """
    スタッフおよびアドミンのアカウント管理用テーブル（生徒は含まない）
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(
        db.String(50), unique=True, nullable=False
    )  # ログインID（メールアドレス）
    password_hash = db.Column(db.String(256), nullable=False)  # ハッシュ化パスワード
    line_user_id = db.Column(
        db.String(100), unique=True, nullable=True
    )  # LINEのユーザーID
    role = db.Column(db.String(20), nullable=False)  # '管理者' または 'スタッフ'
    name = db.Column(db.String(50), nullable=False)  # 氏名
    is_deleted = db.Column(
        db.Boolean, server_default=expression.false(), nullable=False
    )

    # スタッフが記入した学習記録（1対多）
    # ※LearningRecord側の 'writer_staff' バックレフと自動接続されます
    records_written = db.relationship(
        "LearningRecord", backref="writer_staff", foreign_keys="LearningRecord.staff_id"
    )
    staff_profile = db.relationship(
        "Staff", backref="user", uselist=False, cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Staff(db.Model):
    __tablename__ = "staffs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    face_photo_path = db.Column(db.String(255), nullable=True)

    # プロフィール詳細項目（暗号化して保存）
    email = db.Column(EncryptedString(512), nullable=False)
    submission_date = db.Column(EncryptedDate)
    last_name_kanji = db.Column(EncryptedString(512), nullable=False)
    first_name_kanji = db.Column(EncryptedString(512), nullable=False)
    last_name_kana = db.Column(EncryptedString(512))
    first_name_kana = db.Column(EncryptedString(512))
    post_code = db.Column(EncryptedString(512))
    address = db.Column(EncryptedText)
    tel_main = db.Column(EncryptedString(512))
    tel_sub = db.Column(EncryptedString(512))
    exp_jp = db.Column(db.Text)
    exp_other = db.Column(db.Text)
    hobbies = db.Column(db.String(255))
    skills = db.Column(db.String(255))
    qualifications = db.Column(db.String(255))
    intent = db.Column(db.Text)


class Student(db.Model):
    """
    生徒情報テーブル（アカウントとは独立した単体のカルテ）
    """

    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    face_photo_path = db.Column(db.String(255), nullable=False)  # (1)
    name_kana = db.Column(db.String(100), nullable=False)  # (2)
    country_of_origin = db.Column(db.String(50), nullable=False)  # (3)
    native_language = db.Column(db.String(50), nullable=False)  # (4)
    other_languages = db.Column(db.String(100))  # (5)
    occupation = db.Column(db.String(50))  # (6)
    residential_area = db.Column(db.String(50), nullable=False)  # (7)
    jlpt_level = db.Column(db.String(10), nullable=False)  # (8)
    learning_purpose = db.Column(db.Text)  # (9)
    life_troubles = db.Column(db.Text)  # (10)
    how_knew_class = db.Column(db.String(50), nullable=False)  # (11)
    how_knew_class_other = db.Column(db.Text)  # (12)
    is_priority = db.Column(db.Boolean, default=False, nullable=False)  # 優先フラグ
    display_order = db.Column(db.Integer, default=0, nullable=True)  # 出席表・表示順

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 生徒に紐づく学習記録（1対多）
    # ※LearningRecord側の 'student' バックレフと自動接続されます。cascadeにより生徒削除時に記録も消えます。
    learning_records = db.relationship(
        "LearningRecord", backref="student", cascade="all, delete-orphan"
    )


class LearningRecord(db.Model):
    __tablename__ = "learning_records"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    staff_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # 画像の項目に対応
    lesson_date = db.Column(db.Date, default=datetime.utcnow)  # レッスン日
    textbook_progress = db.Column(db.String(50))  # 第〇回目（選択式）
    today_learning_content = db.Column(db.Text)  # 学習内容（一般）
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)


class Meeting(db.Model):
    __tablename__ = "meetings"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)  # ミーティングタイトル
    date = db.Column(db.Date, nullable=False)
    pdf_path = db.Column(db.String(255), nullable=True)
    content = db.Column(db.Text, nullable=False)  # 議事録内容
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))  # 作成者
    attachments = db.relationship(
        "Attachment", backref="meeting", lazy=True, cascade="all, delete-orphan"
    )


class Attachment(db.Model):
    __tablename__ = "attachments"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)  # 保存時のファイル名
    original_name = db.Column(db.String(255), nullable=False)  # 元のファイル名
    meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)


class TextbookOrder(db.Model):
    """
    テキストブック発注テーブル
    """
    __tablename__ = "textbook_orders"

    TEXTBOOK_FIELDS = [
        ("zero_week_1", "ゼロ初級者向けテキストブック 第1週"),
        ("zero_week_2", "ゼロ初級者向けテキストブック 第2週"),
        ("zero_week_3", "ゼロ初級者向けテキストブック 第3週"),
        ("zero_week_4", "ゼロ初級者向けテキストブック 第4週"),
        ("zero_week_5", "ゼロ初級者向けテキストブック 第5週"),
        ("hiragana", "「ひらがな」注文部数"),
        ("katakana", "「カタカナ」注文部数"),
        ("nihongo_kaiwa_1", "「にほんごかいわ 1」注文部数"),
        ("nihongo_shiori", "「にほんごしおり」注文部数"),
        ("kanji_1", "「かんじ 1」注文部数"),
        ("hajimete_kanji_2", "「はじめてのかんじ その2」注文部数"),
        ("hajimete_kanji_3", "「はじめてのかんじ その3」注文部数"),
        ("hajimete_kanji_4", "「はじめてのかんじ その4」注文部数"),
        ("hajimete_kanji_5", "「はじめてのかんじ その5」注文部数"),
        ("nihongo_yomimono_shokyu_1", "「にほんご よみもの 初級1」注文部数"),
        ("nihongo_yomimono_chukyu_1", "「にほんご よみもの 中級1」注文部数"),
        ("nihongo_yomimono_chukyu_2", "「にほんご よみもの 中級2」注文部数"),
        ("hiragana_katakana_sheet", "「ひらがなカタカナ一覧シート」注文部数"),
    ]

    id = db.Column(db.Integer, primary_key=True)
    staff_name = db.Column(db.String(100), nullable=False)  # 発注担当者氏名
    staff_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # 各テキストの注文部数（0以上の整数）
    zero_week_1 = db.Column(db.Integer, default=0, nullable=False)
    zero_week_2 = db.Column(db.Integer, default=0, nullable=False)
    zero_week_3 = db.Column(db.Integer, default=0, nullable=False)
    zero_week_4 = db.Column(db.Integer, default=0, nullable=False)
    zero_week_5 = db.Column(db.Integer, default=0, nullable=False)
    hiragana = db.Column(db.Integer, default=0, nullable=False)
    katakana = db.Column(db.Integer, default=0, nullable=False)
    nihongo_kaiwa_1 = db.Column(db.Integer, default=0, nullable=False)
    nihongo_shiori = db.Column(db.Integer, default=0, nullable=False)
    kanji_1 = db.Column(db.Integer, default=0, nullable=False)
    hajimete_kanji_2 = db.Column(db.Integer, default=0, nullable=False)
    hajimete_kanji_3 = db.Column(db.Integer, default=0, nullable=False)
    hajimete_kanji_4 = db.Column(db.Integer, default=0, nullable=False)
    hajimete_kanji_5 = db.Column(db.Integer, default=0, nullable=False)
    nihongo_yomimono_shokyu_1 = db.Column(db.Integer, default=0, nullable=False)
    nihongo_yomimono_chukyu_1 = db.Column(db.Integer, default=0, nullable=False)
    nihongo_yomimono_chukyu_2 = db.Column(db.Integer, default=0, nullable=False)
    hiragana_katakana_sheet = db.Column(db.Integer, default=0, nullable=False)

    note = db.Column(db.Text, nullable=True)  # 備考・連絡事項
    status = db.Column(db.String(50), default="注文済み", nullable=False)  # 注文済み / 準備中 / 完了 / キャンセル
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 発注者アカウントとのリレーション（任意）
    staff_user = db.relationship("User", foreign_keys=[staff_id], backref="textbook_orders")

    @property
    def total_quantity(self):
        """合計注文部数を計算"""
        return sum(
            getattr(self, field_key, 0) or 0
            for field_key, _ in self.TEXTBOOK_FIELDS
        )

    def items_summary(self):
        """1部以上注文された教材のサマリーリスト"""
        items = []
        for field_key, label in self.TEXTBOOK_FIELDS:
            qty = getattr(self, field_key, 0) or 0
            if qty > 0:
                items.append({"key": field_key, "label": label, "quantity": qty})
        return items

    def to_dict(self):
        """APIレスポンス用の辞書形式"""
        return {
            "id": self.id,
            "staff_name": self.staff_name,
            "staff_id": self.staff_id,
            "items": {
                field_key: getattr(self, field_key, 0) or 0
                for field_key, _ in self.TEXTBOOK_FIELDS
            },
            "ordered_items": self.items_summary(),
            "total_quantity": self.total_quantity,
            "note": self.note,
            "status": self.status,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }
