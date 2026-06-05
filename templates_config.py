"""全ルーターで共有するJinja2Templatesインスタンス。
csrf_token グローバルはここで一元登録する。"""
from fastapi import Request
from fastapi.templating import Jinja2Templates
from auth import generate_csrf_token

templates = Jinja2Templates(directory="templates")

def _jinja_csrf_token(request: Request) -> str:
    token = request.cookies.get("session", "")
    return generate_csrf_token(token)

templates.env.globals["csrf_token"] = _jinja_csrf_token
