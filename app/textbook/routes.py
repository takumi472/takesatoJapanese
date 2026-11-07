import os
from datetime import datetime
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    current_app,
)
from flask_login import current_user, login_required
from app import db
from app.models import TextbookOrder, User, Staff

textbook_bp = Blueprint("textbook", __name__)

# 発注フォームに表示するテキストブック項目の一覧（表示順・ラベル）
TEXTBOOK_ITEMS = [
    {
        "key": "zero_week_1",
        "label": "ゼロ初級者向けテキストブック　第1週",
        "description": "第1週目のゼロ初級者用教材",
    },
    {
        "key": "zero_week_2",
        "label": "ゼロ初級者向けテキストブック　第2週",
        "description": "第2週目のゼロ初級者用教材",
    },
    {
        "key": "zero_week_3",
        "label": "ゼロ初級者向けテキストブック　第3週",
        "description": "第3週目のゼロ初級者用教材",
    },
    {
        "key": "zero_week_4",
        "label": "ゼロ初級者向けテキストブック　第4週",
        "description": "第4週目のゼロ初級者用教材",
    },
    {
        "key": "zero_week_5",
        "label": "ゼロ初級者向けテキストブック　第5週",
        "description": "第5週目のゼロ初級者用教材",
    },
    {
        "key": "hiragana",
        "label": "「ひらがな」注文部数",
        "description": "ひらがな基礎教材",
    },
    {
        "key": "katakana",
        "label": "「カタカナ」注文部数",
        "description": "カタカナ基礎教材",
    },
    {
        "key": "nihongo_kaiwa_1",
        "label": "「にほんごかいわ 1」注文部数",
        "description": "日常会話テキスト 1",
    },
    {
        "key": "nihongo_shiori",
        "label": "「にほんごしおり」注文部数",
        "description": "日本語しおり（入門ガイド）",
    },
    {
        "key": "kanji_1",
        "label": "「かんじ 1」注文部数",
        "description": "漢字学習 1",
    },
    {
        "key": "hajimete_kanji_2",
        "label": "「はじめてのかんじ　その2」注文部数",
        "description": "はじめての漢字シリーズ その2",
    },
    {
        "key": "hajimete_kanji_3",
        "label": "「はじめてのかんじ　その3」注文部数",
        "description": "はじめての漢字シリーズ その3",
    },
    {
        "key": "hajimete_kanji_4",
        "label": "「はじめてのかんじ　その４」注文部数",
        "description": "はじめての漢字シリーズ その4",
    },
    {
        "key": "hajimete_kanji_5",
        "label": "「はじめてのかんじ　その５」注文部数",
        "description": "はじめての漢字シリーズ その5",
    },
    {
        "key": "nihongo_yomimono_shokyu_1",
        "label": "「にほんご よみもの 初級１」注文部数",
        "description": "日本語読みもの 初級1",
    },
    {
        "key": "nihongo_yomimono_chukyu_1",
        "label": "「にほんご よみもの 中級１」注文部数",
        "description": "日本語読みもの 中級1",
    },
    {
        "key": "nihongo_yomimono_chukyu_2",
        "label": "「にほんご よみもの 中級２」注文部数",
        "description": "日本語読みもの 中級2",
    },
    {
        "key": "hiragana_katakana_sheet",
        "label": "「ひらがなカタカナ一覧シート」注文部数",
        "description": "ひらがな・カタカナ一覧表シート",
    },
]

# 部数選択のオプション候補
QUANTITY_CHOICES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20]


def _escape_like(text: str) -> str:
    """LIKE/ILIKE クエリのワイルドカード特殊文字（%、_、\）をエスケープして安全にする"""
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _is_admin():
    """現在のユーザーが管理者権限（adminまたは管理者）を持つかを判定"""
    return current_user.is_authenticated and current_user.role in ["admin", "管理者"]


# =========================================================================
# Web 画面用ルーティング
# =========================================================================

@textbook_bp.route("/order", methods=["GET", "POST"])
@login_required
def order_form():
    """テキストブック発注フォーム画面（Googleフォーム風UI）"""
    # スタッフ一覧を取得（氏名選択肢用）
    staff_members = User.query.filter_by(is_deleted=False).order_by(User.name).all()

    if request.method == "POST":
        # 通常のHTMLフォーム送信時の処理
        staff_name = (request.form.get("staff_name") or "").strip()
        if not staff_name:
            flash("発注担当者氏名は必須項目です。", "danger")
            return redirect(url_for("textbook.order_form"))

        staff_id = request.form.get("staff_id")
        matched_user = User.query.filter_by(name=staff_name).first() if not staff_id else None
        if matched_user:
            staff_id = matched_user.id
        elif current_user.is_authenticated and current_user.name == staff_name:
            staff_id = current_user.id

        order_data = {}
        for item in TEXTBOOK_ITEMS:
            key = item["key"]
            val = request.form.get(key, 0)
            try:
                order_data[key] = max(0, int(val))
            except (ValueError, TypeError):
                order_data[key] = 0

        note = request.form.get("note", "").strip()

        order = TextbookOrder(
            staff_name=staff_name,
            staff_id=staff_id if staff_id else (current_user.id if current_user.is_authenticated else None),
            note=note,
            **order_data,
        )

        db.session.add(order)
        db.session.commit()

        flash("テキストブックの発注を受け付けました。", "success")
        return redirect(url_for("textbook.order_list"))

    # GETリクエスト時
    current_staff_name = current_user.name if current_user.is_authenticated else ""
    current_user_email = current_user.username if current_user.is_authenticated else ""

    return render_template(
        "textbook/order.html",
        textbook_items=TEXTBOOK_ITEMS,
        quantity_choices=QUANTITY_CHOICES,
        staff_members=staff_members,
        current_staff_name=current_staff_name,
        current_user_email=current_user_email,
    )


@textbook_bp.route("/orders", methods=["GET"])
@textbook_bp.route("/list", methods=["GET"])
@login_required
def order_list():
    """発注一覧・管理画面"""
    status_filter = request.args.get("status")
    query = TextbookOrder.query

    if status_filter:
        query = query.filter_by(status=status_filter)

    orders = query.order_by(TextbookOrder.created_at.desc()).all()
    return render_template(
        "textbook/list.html",
        orders=orders,
        status_filter=status_filter,
        textbook_items=TEXTBOOK_ITEMS,
        is_admin=_is_admin(),
    )


@textbook_bp.route("/order/<int:order_id>", methods=["GET"])
@login_required
def order_detail(order_id):
    """発注詳細画面"""
    order = TextbookOrder.query.get_or_404(order_id)
    return render_template(
        "textbook/detail.html",
        order=order,
        textbook_items=TEXTBOOK_ITEMS,
        is_admin=_is_admin(),
    )


@textbook_bp.route("/order/<int:order_id>/edit", methods=["GET", "POST"])
@login_required
def edit_order(order_id):
    """発注編集画面（全スタッフ操作可能）"""
    order = TextbookOrder.query.get_or_404(order_id)
    staff_members = User.query.filter_by(is_deleted=False).order_by(User.name).all()

    if request.method == "POST":
        staff_name = (request.form.get("staff_name") or "").strip()
        if not staff_name:
            flash("発注担当者氏名は必須項目です。", "danger")
            return redirect(url_for("textbook.edit_order", order_id=order.id))

        staff_id = request.form.get("staff_id")
        matched_user = User.query.filter_by(name=staff_name).first() if not staff_id else None
        if matched_user:
            order.staff_id = matched_user.id
        elif staff_id:
            try:
                order.staff_id = int(staff_id)
            except (ValueError, TypeError):
                pass

        order.staff_name = staff_name

        # 各テキストブックの注文部数を更新
        for item in TEXTBOOK_ITEMS:
            key = item["key"]
            val = request.form.get(key, 0)
            try:
                setattr(order, key, max(0, int(val)))
            except (ValueError, TypeError):
                setattr(order, key, 0)

        order.note = (request.form.get("note") or "").strip()

        # 管理者の場合のみステータス更新もフォームから許可
        if _is_admin():
            new_status = request.form.get("status")
            if new_status in ["注文済み", "準備中", "完了", "キャンセル"]:
                order.status = new_status

        order.updated_at = datetime.utcnow()
        db.session.commit()

        flash(f"発注ID #{order.id} の注文内容を更新しました。", "success")
        return redirect(url_for("textbook.order_detail", order_id=order.id))

    return render_template(
        "textbook/edit.html",
        order=order,
        textbook_items=TEXTBOOK_ITEMS,
        quantity_choices=QUANTITY_CHOICES,
        staff_members=staff_members,
        is_admin=_is_admin(),
    )


@textbook_bp.route("/order/<int:order_id>/status", methods=["POST"])
@login_required
def update_status(order_id):
    """ステータス更新（管理者のみ許可）"""
    if not _is_admin():
        flash("ステータスを変更する権限がありません（管理者のみ可能です）。", "danger")
        return redirect(request.referrer or url_for("textbook.order_list"))

    order = TextbookOrder.query.get_or_404(order_id)
    new_status = request.form.get("status")
    valid_statuses = ["注文済み", "準備中", "完了", "キャンセル"]
    if new_status in valid_statuses:
        order.status = new_status
        db.session.commit()
        flash(f"発注ID #{order.id} のステータスを「{new_status}」に更新しました。", "success")
    else:
        flash("無効なステータスです。", "danger")
    return redirect(request.referrer or url_for("textbook.order_list"))


@textbook_bp.route("/order/<int:order_id>/delete", methods=["POST"])
@login_required
def delete_order(order_id):
    """発注削除（管理者のみ許可）"""
    if not _is_admin():
        flash("発注を削除する権限がありません（管理者のみ可能です）。", "danger")
        return redirect(request.referrer or url_for("textbook.order_list"))

    order = TextbookOrder.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()
    flash(f"発注ID #{order_id} を削除しました。", "info")
    return redirect(url_for("textbook.order_list"))


# =========================================================================
# REST API ルーティング
# =========================================================================

@textbook_bp.route("/api/items", methods=["GET"])
def api_get_items():
    """注文可能な教材マスター一覧を返す"""
    return jsonify({
        "success": True,
        "items": TEXTBOOK_ITEMS,
        "quantity_choices": QUANTITY_CHOICES,
    })


@textbook_bp.route("/api/orders", methods=["GET"])
@login_required
def api_get_orders():
    """発注一覧を取得するAPI"""
    status = request.args.get("status")
    staff_name = request.args.get("staff_name")
    limit = request.args.get("limit", default=50, type=int)
    offset = request.args.get("offset", default=0, type=int)

    query = TextbookOrder.query
    if status:
        query = query.filter_by(status=status)
    if staff_name:
        safe_staff_name = _escape_like(staff_name.strip())
        query = query.filter(TextbookOrder.staff_name.ilike(f"%{safe_staff_name}%"))

    total = query.count()
    orders = query.order_by(TextbookOrder.created_at.desc()).offset(offset).limit(limit).all()

    return jsonify({
        "success": True,
        "total": total,
        "orders": [order.to_dict() for order in orders],
        "limit": limit,
        "offset": offset,
    })


@textbook_bp.route("/api/orders", methods=["POST"])
def api_create_order():
    """
    新規発注を作成するAPI
    JSON形式またはForm-Dataに対応
    Request Body:
    {
      "staff_name": "氏名",
      "staff_id": 1 (任意),
      "items": {
        "zero_week_1": 2,
        "hiragana": 5, ...
      },
      "note": "メモ" (任意)
    }
    """
    data = request.get_json(silent=True) or request.form.to_dict()

    staff_name = (data.get("staff_name") or "").strip()
    if not staff_name:
        return jsonify({
            "success": False,
            "error": "発注担当者氏名は必須です。",
        }), 400

    staff_id = data.get("staff_id")
    if not staff_id and current_user.is_authenticated:
        staff_id = current_user.id

    # 部数の展開
    items_data = data.get("items") or {}
    order_values = {}
    for item in TEXTBOOK_ITEMS:
        key = item["key"]
        # itemsオブジェクト内、またはトップレベルキーから取得
        val = items_data.get(key) if key in items_data else data.get(key, 0)
        try:
            order_values[key] = max(0, int(val))
        except (ValueError, TypeError):
            order_values[key] = 0

    total_qty = sum(order_values.values())
    if total_qty == 0:
        return jsonify({
            "success": False,
            "error": "少なくとも1部以上のテキストブックを選択してください。",
        }), 400

    note = data.get("note", "").strip()

    try:
        new_order = TextbookOrder(
            staff_name=staff_name,
            staff_id=staff_id,
            note=note,
            status="注文済み",
            **order_values,
        )
        db.session.add(new_order)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "テキストブックの発注が正常に完了しました。",
            "order": new_order.to_dict(),
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Textbook order creation failed: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "発注処理中にエラーが発生しました。",
        }), 500


@textbook_bp.route("/api/orders/<int:order_id>", methods=["GET"])
@login_required
def api_get_order(order_id):
    """単一の発注詳細を取得するAPI"""
    order = TextbookOrder.query.get(order_id)
    if not order:
        return jsonify({"success": False, "error": "指定された発注が見つかりません。"}), 404
    return jsonify({"success": True, "order": order.to_dict()})


@textbook_bp.route("/api/orders/<int:order_id>", methods=["PUT", "PATCH"])
@login_required
def api_update_order(order_id):
    """発注内容を更新するAPI（全スタッフ操作可能）"""
    order = TextbookOrder.query.get(order_id)
    if not order:
        return jsonify({"success": False, "error": "指定された発注が見つかりません。"}), 404

    data = request.get_json(silent=True) or request.form.to_dict()

    if "staff_name" in data:
        name = data["staff_name"].strip()
        if not name:
            return jsonify({"success": False, "error": "発注担当者氏名は必須です。"}), 400
        order.staff_name = name

    if "staff_id" in data:
        try:
            order.staff_id = int(data["staff_id"]) if data["staff_id"] else None
        except (ValueError, TypeError):
            pass

    if "note" in data:
        order.note = data["note"].strip()

    items_data = data.get("items")
    for item in TEXTBOOK_ITEMS:
        key = item["key"]
        if items_data and key in items_data:
            val = items_data[key]
        elif key in data:
            val = data[key]
        else:
            continue
        try:
            setattr(order, key, max(0, int(val)))
        except (ValueError, TypeError):
            setattr(order, key, 0)

    if _is_admin() and "status" in data:
        if data["status"] in ["注文済み", "準備中", "完了", "キャンセル"]:
            order.status = data["status"]

    order.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"発注ID #{order_id} を更新しました。",
        "order": order.to_dict(),
    })


@textbook_bp.route("/api/orders/<int:order_id>/status", methods=["PATCH", "POST"])
@login_required
def api_update_order_status(order_id):
    """発注ステータスを更新するAPI（管理者のみ許可）"""
    if not _is_admin():
        return jsonify({"success": False, "error": "ステータスを変更するには管理者権限が必要です。"}), 403

    order = TextbookOrder.query.get(order_id)
    if not order:
        return jsonify({"success": False, "error": "指定された発注が見つかりません。"}), 404

    data = request.get_json(silent=True) or request.form.to_dict()
    new_status = data.get("status")
    valid_statuses = ["注文済み", "準備中", "完了", "キャンセル"]
    if new_status not in valid_statuses:
        return jsonify({
            "success": False,
            "error": f"無効なステータスです。有効値: {', '.join(valid_statuses)}",
        }), 400

    order.status = new_status
    db.session.commit()
    return jsonify({
        "success": True,
        "message": f"ステータスを「{new_status}」に更新しました。",
        "order": order.to_dict(),
    })


@textbook_bp.route("/api/orders/<int:order_id>", methods=["DELETE"])
@login_required
def api_delete_order(order_id):
    """発注を削除するAPI（管理者のみ許可）"""
    if not _is_admin():
        return jsonify({"success": False, "error": "発注を削除するには管理者権限が必要です。"}), 403

    order = TextbookOrder.query.get(order_id)
    if not order:
        return jsonify({"success": False, "error": "指定された発注が見つかりません。"}), 404

    db.session.delete(order)
    db.session.commit()
    return jsonify({
        "success": True,
        "message": f"発注ID #{order_id} を削除しました。",
    })

