from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    """
    スタッフおよびアドミンのアカウント管理用テーブル（生徒は含まない）
    """
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False) # ログインID（メールアドレス）
    password_hash = db.Column(db.String(256), nullable=False)        # ハッシュ化パスワード
    role = db.Column(db.String(20), nullable=False)                  # 'admin' または 'staff'
    name = db.Column(db.String(50), nullable=False)                  # 氏名

    # スタッフが記入した学習記録（1対多）
    # ※LearningRecord側の 'writer_staff' バックレフと自動接続されます
    records_written = db.relationship('LearningRecord', backref='writer_staff', foreign_keys='LearningRecord.staff_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Student(db.Model):
    """
    生徒情報テーブル（アカウントとは独立した単体のカルテ）
    """
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)    
    face_photo_path = db.Column(db.String(255), nullable=False)      # (1)
    name_kana = db.Column(db.String(100), nullable=False)            # (2)
    country_of_origin = db.Column(db.String(50), nullable=False)      # (3)
    native_language = db.Column(db.String(50), nullable=False)        # (4)
    other_languages = db.Column(db.String(100))                      # (5)
    occupation = db.Column(db.String(50))                            # (6)
    residential_area = db.Column(db.String(50), nullable=False)      # (7)
    jlpt_level = db.Column(db.String(10), nullable=False)            # (8)
    learning_purpose = db.Column(db.Text)                            # (9)
    life_troubles = db.Column(db.Text)                               # (10)
    how_knew_class = db.Column(db.String(50), nullable=False)        # (11)
    how_knew_class_other = db.Column(db.Text)                         # (12)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 生徒に紐づく学習記録（1対多）
    # ※LearningRecord側の 'student' バックレフと自動接続されます。cascadeにより生徒削除時に記録も消えます。
    learning_records = db.relationship('LearningRecord', backref='student', cascade='all, delete-orphan')


class LearningRecord(db.Model):
    """
    学習記録テーブル
    """
    __tablename__ = 'learning_records'

    id = db.Column(db.Integer, primary_key=True)
    
    # 【修正箇所①】
    # 参照先テーブル名を '__tablename__' で指定した 'students.id' に統一し、タイポを修正。
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False) 
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)                          
    
    today_learning_content = db.Column(db.Text, nullable=True) # (13)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 【修正箇所②】
    # 循環定義による競合を防ぐため、ここにあった db.relationship('StudentProfile', ...) は削除しました。
    # Studentクラス側の db.relationship(..., backref='student') によって、
    # 自動的に record.student で生徒データにアクセスできるようになっています。