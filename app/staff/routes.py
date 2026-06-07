# app/staff/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from app.models import db, User, Staff
from werkzeug.security import generate_password_hash
from datetime import datetime

staff_bp = Blueprint("staff", __name__)

# スタッフの新規登録（UserとStaffを同時にインサート）
import os
from flask import current_app
from werkzeug.utils import secure_filename


# 許可する拡張子のチェック関数
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"png", "jpg", "jpeg", "gif"}


# スタッフの新規登録（写真登録対応）
@staff_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_staff():
    if request.method == "POST":
        email = request.form.get("email")
        plain_password = request.form.get("password")

        last_name = request.form.get("last_name_kanji", "").strip()
        first_name = request.form.get("first_name_kanji", "").strip()

        if last_name or first_name:
            full_name = f"{last_name} {first_name}".strip()
        else:
            full_name = email.split("@")[0] if email else "新規スタッフ"

        if User.query.filter_by(username=email).first():
            flash("このGmailアドレスは既にシステムアカウントとして登録されています。", "danger")
            return redirect(url_for("staff.create_staff"))

        # --- ▼ 顔写真ファイルの保存処理 ▼ ---
        filename = None
        if "face_photo" in request.files:
            file = request.files["face_photo"]
            if file and file.filename != "":
                if allowed_file(file.filename):
                    # ファイル名の競合を防ぐため、タイムスタンプを付与して安全な名前に変換
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S_")
                    filename = timestamp + secure_filename(file.filename)

                    # 保存先フォルダ (app/static/uploads) の絶対パスを作成・存在確認
                    upload_folder = os.path.join(current_app.root_path, "static", "uploads")
                    os.makedirs(upload_folder, exist_ok=True)

                    # ファイルを保存
                    file.save(os.path.join(upload_folder, filename))
                else:
                    flash("許可されていないファイル形式です。(png, jpg, jpeg, gif のみ)", "danger")
                    return redirect(url_for("staff.create_staff"))
        # --- ▲ 顔写真ファイルの保存処理 ▲ ---

        try:
            # 1. ユーザーアカウント作成
            new_user = User(
                username=email, role="staff", name=full_name, password_hash=generate_password_hash(plain_password)
            )
            db.session.add(new_user)
            db.session.flush()  # new_user.id を確定させる

            # 2. スタッフプロフィール作成 (確定した face_photo_path を登録)
            new_staff = Staff(
                user_id=new_user.id,
                email=email,
                face_photo_path=filename,  # ★ データベースにファイル名を保存
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

            sub_date = request.form.get("submission_date")
            if sub_date:
                new_staff.submission_date = datetime.strptime(sub_date, "%Y-%m-%d").date()

            db.session.add(new_staff)
            db.session.commit()

            flash(f"{full_name} さんのスタッフ登録が完了しました。", "success")
            return redirect(url_for("staff.staff_list"))

        except Exception as e:
            db.session.rollback()
            flash(f"登録中にエラーが発生しました: {str(e)}", "danger")

    return render_template("staff/edit.html", staff=None)


# スタッフ情報の編集（写真の差し替え変更に対応）
@staff_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_staff(id):
    staff = Staff.query.get_or_404(id)
    if not current_user.is_admin and current_user.id != staff.user_id:
        flash("他のユーザーの情報を編集する権限がありません。")
        return redirect(url_for('staff.index'))

    if request.method == "POST":
        # --- ▼ 編集時の顔写真アップデート処理 ▼ ---
        if "face_photo" in request.files:
            file = request.files["face_photo"]
            if file and file.filename != "":
                if allowed_file(file.filename):
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S_")
                    filename = timestamp + secure_filename(file.filename)

                    upload_folder = os.path.join(current_app.root_path, "static", "uploads")
                    os.makedirs(upload_folder, exist_ok=True)

                    file.save(os.path.join(upload_folder, filename))
                    staff.face_photo_path = filename  # ★ 新しい写真パスに上書き
                else:
                    flash("許可されていないファイル形式です。(png, jpg, jpeg, gif のみ)", "danger")
                    return render_template("staff/edit.html", staff=staff)
        # --- ▲ 編集時の顔写真アップデート処理 ▲ ---

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

            sub_date = request.form.get("submission_date")
            if sub_date:
                staff.submission_date = datetime.strptime(sub_date, "%Y-%m-%d").date()

            db.session.commit()
            flash("スタッフ情報を更新しました。", "success")
            return redirect(url_for("staff.staff_list"))

        except Exception as e:
            db.session.rollback()
            flash(f"更新中にエラーが発生しました: {str(e)}", "danger")

    return render_template("staff/edit.html", staff=staff)


@staff_bp.route("/")
@login_required
def staff_list():
    # staffsテーブルから、IDの昇順で全スタッフのレコードを取得
    all_staff = Staff.query.order_by(Staff.id.asc()).all()

    # テンプレート（list.html）にスタッフ一覧データを渡してレンダリング
    return render_template("staff/list.html", staff_list=all_staff, current_user=current_user)
