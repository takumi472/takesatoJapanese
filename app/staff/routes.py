# app/staff/routes.py
from flask import Blueprint

staff_bp = Blueprint('staff', __name__)

@staff_bp.route('/')
def staff_list():
    return "スタッフ情報一覧画面"

@staff_bp.route('/create')
def create_staff():
    return "スタッフ登録画面"

@staff_bp.route('/<int:id>/update')
def update_staff(id):
    return f"スタッフ更新画面 (ID: {id})"