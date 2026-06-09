# app/staff/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required # login_requiredは使用されているため残す
from app.models import db, User, Staff
from werkzeug.security import generate_password_hash
from datetime import datetime
import cloudinary
import cloudinary.uploader
from flask import current_app # current_appはログなどで使用するため残す

staff_bp = Blueprint("staff", __name__)

# --- 定数定義 ---
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
CLOUDINARY_STAFF_FOLDER = "staffs"
CLOUDINARY_EAGER_TRANSFORMATION = [
    {
        "crop": "thumb",  # 顔がきれいに収まるサムネイルモード
        "gravity": "face",  # AIによる顔認識（高精度なら "adv_face"）
        "zoom": 0.7,  # 顔を大きくする（数字が小さいほどドアップ）
        "width": 200,  # 最終的な横幅
        "height": 200,  # 最終的な縦幅
        "fetch_format": "auto",  # PWA・スマホ用に自動軽量化
        "quality": "auto",  # 画質を自動最適化
    }
]

# --- ヘルパー関数 ---
def allowed_file(filename):
    """ファイル名が許可された拡張子を持つかチェックする"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def _upload_face_photo(file):
    """
    顔写真をCloudinaryにアップロードし、そのURLを返す。
    許可されていないファイル形式の場合はNoneを返す。
    """
    if file and file.filename != "":
        if allowed_file(file.filename):
            try:
                upload_result = cloudinary.uploader.upload(
                    file,
                    folder=CLOUDINARY_STAFF_FOLDER,
                    eager=CLOUDINARY_EAGER_TRANSFORMATION,
                )
                # eager変換が適用されたURLを取得
                return upload_result.get("eager")[0].get("secure_url")
            except Exception as e:
                current_app.logger.error(f"Cloudinary upload failed: {e}", exc_info=True)
                flash("顔写真のアップロード中にエラーが発生しました。", "danger")
                return None
        else:
            flash(f"許可されていないファイル形式です。({', '.join(ALLOWED_EXTENSIONS)} のみ)", "danger")
            return None
    return None

def _parse_date_or_none(date_str):
    """日付文字列をdatetime.dateオブジェクトにパースする。無効な場合はNoneを返す。"""
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            current_app.logger.warning(f"Invalid date format received: {date_str}")
            return None
    return None

# --- ルート定義 ---
@staff_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_staff():
    # 管理者権限チェック（必要であれば）
    if current_user.role != 'admin':
        flash('スタッフを登録する権限がありません。', 'danger')
        return redirect(url_for('staff.staff_list')) # または適切なリダイレクト先

    if request.method == "POST":
        email = request.form.get("email")
        plain_password = request.form.get("password")

        last_name = request.form.get("last_name_kanji", "").strip()
        first_name = request.form.get("first_name_kanji", "").strip()

        # 必須フィールドのバリデーション
        if not email or not plain_password:
            flash("メールアドレスとパスワードは必須です。", "danger")
            return render_template("staff/edit.html", staff=None)

        # ユーザー名（メールアドレス）の重複チェック
        if User.query.filter_by(username=email).first():
            flash("このGmailアドレスは既にシステムアカウントとして登録されています。", "danger")
            return render_template("staff/edit.html", staff=None)

        # フルネームの生成
        full_name = f"{last_name} {first_name}".strip()
        if not full_name:
            full_name = email.split("@")[0]

        # 顔写真のアップロード
        face_photo_path = _upload_face_photo(request.files.get("face_photo"))
        if face_photo_path is None and "face_photo" in request.files and request.files["face_photo"].filename != "":
            # アップロードに失敗したが、ファイルが選択されていた場合
            return render_template("staff/edit.html", staff=None)

        try:
            # 1. ユーザーアカウント作成
            new_user = User(
                username=email,
                role="staff",
                name=full_name,
                password_hash=generate_password_hash(plain_password),
            )
            db.session.add(new_user)
            db.session.flush()  # new_user.id を確定させる

            # 2. スタッフプロフィール作成 (確定した face_photo_path を登録)
            new_staff = Staff(
                user_id=new_user.id,
                email=email,
                face_photo_path=face_photo_path,  # ★ データベースにファイル名を保存
                last_name_kanji=last_name,
                first_name_kanji=first_name,
                last_name_kana=request.form.get("last_name_kana"),
                first_name_kana=request.form.get("first_name_kana"),
                post_code=request.form.get("post_code"),
                address=request.form.get("address"),
                tel_main=request.form.get("tel_main"),
                tel_sub=request.form.get("tel_sub"),
                exp_jp=request.form.get("exp_jp"),
                exp_other=request.form.get("exp_other"),
                hobbies=request.form.get("hobbies"),
                skills=request.form.get("skills"),
                qualifications=request.form.get("qualifications"),
                intent=request.form.get("intent"),
            )
            
            new_staff.submission_date = _parse_date_or_none(request.form.get("submission_date"))

            db.session.add(new_staff)
            db.session.commit()

            flash(f"{full_name} さんのスタッフ登録が完了しました。", "success")
            return redirect(url_for("staff.staff_list"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating staff: {e}", exc_info=True)
            flash(f"登録中にエラーが発生しました: {str(e)}", "danger")

    return render_template("staff/edit.html", staff=None)


# スタッフ情報の編集（写真の差し替え変更に対応）
@staff_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_staff(id):
    staff = Staff.query.get_or_404(id)
    
    # 権限チェック: 管理者でない、かつ自身のスタッフ情報でない場合は編集不可
    if current_user.role != "admin" and current_user.id != staff.user_id:
        flash("他のユーザーの情報を編集する権限がありません。")
        return redirect(url_for("staff.staff_list")) # 適切なリダイレクト先

    if request.method == "POST":
        # 顔写真のアップロード（既存のパスを上書き）
        new_face_photo_path = _upload_face_photo(request.files.get("face_photo"))
        if new_face_photo_path is not None:
            staff.face_photo_path = new_face_photo_path
        elif "face_photo" in request.files and request.files["face_photo"].filename != "":
            # アップロードに失敗したが、ファイルが選択されていた場合
            return render_template("staff/edit.html", staff=staff)

        try:
            staff.last_name_kanji = request.form.get("last_name_kanji")
            staff.first_name_kanji = request.form.get("first_name_kanji")
            staff.last_name_kana = request.form.get("last_name_kana")
            staff.first_name_kana = request.form.get("first_name_kana")
            staff.post_code = request.form.get("post_code")
            staff.address = request.form.get("address")
            staff.tel_main = request.form.get("tel_main")
            staff.tel_sub = request.form.get("tel_sub")
            staff.exp_jp = request.form.get("exp_jp")
            staff.exp_other = request.form.get("exp_other")
            staff.hobbies = request.form.get("hobbies")
            staff.skills = request.form.get("skills")
            staff.qualifications = request.form.get("qualifications")
            staff.intent = request.form.get("intent")

            staff.submission_date = _parse_date_or_none(request.form.get("submission_date"))

            db.session.commit()
            flash("スタッフ情報を更新しました。", "success")
            return redirect(url_for("staff.staff_list"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating staff {id}: {e}", exc_info=True)
            flash(f"更新中にエラーが発生しました: {str(e)}", "danger")

    return render_template("staff/edit.html", staff=staff)


@staff_bp.route("/")
@login_required
def staff_list():
    # staffsテーブルから、IDの昇順で全スタッフのレコードを取得
    all_staff = Staff.query.order_by(Staff.id.asc()).all()

    # テンプレート（list.html）にスタッフ一覧データを渡してレンダリング
    return render_template("staff/list.html", staff_list=all_staff, current_user=current_user)
