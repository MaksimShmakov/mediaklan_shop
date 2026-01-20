from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, validate_password, verify_password
from app.core.templates import templates
from app.models import User
from app.services.auth import normalize_tg_username

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def root(request: Request) -> RedirectResponse:
    if request.session.get("tg_username"):
        return RedirectResponse("/shops", status_code=303)
    return RedirectResponse("/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
def login(
    request: Request,
    tg_username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    normalized = normalize_tg_username(tg_username)
    if not normalized:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Введите корректный tg_username"},
            status_code=400,
        )
    user = db.execute(
        select(User).where(User.tg_username == normalized)
    ).scalar_one_or_none()
    if not user or not user.password_hash:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Аккаунт не найден. Зарегистрируйтесь.",
            },
            status_code=400,
        )
    if not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный пароль"},
            status_code=400,
        )
    request.session["tg_username"] = normalized
    return RedirectResponse("/shops", status_code=303)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
def register(
    request: Request,
    tg_username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    normalized = normalize_tg_username(tg_username)
    if not normalized:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Введите корректный tg_username"},
            status_code=400,
        )
    if password != password_confirm:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Пароли не совпадают"},
            status_code=400,
        )
    password_error = validate_password(password)
    if password_error:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": password_error},
            status_code=400,
        )
    user = db.execute(
        select(User).where(User.tg_username == normalized)
    ).scalar_one_or_none()
    if user and user.password_hash:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Пользователь уже зарегистрирован"},
            status_code=400,
        )
    if not user:
        user = User(tg_username=normalized, points=0)
        db.add(user)
    user.password_hash = hash_password(password)
    db.commit()
    request.session["tg_username"] = normalized
    return RedirectResponse("/shops", status_code=303)


@router.get("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
