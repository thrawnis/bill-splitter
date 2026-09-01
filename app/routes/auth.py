from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import create_session, get_current_user, hash_password, safe_internal_path, set_session_cookie, verify_password
from ..database import get_db
from ..models import User, UserSession
from .common import templates

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login_page(request: Request, next: str = "/dashboard", current_user=Depends(get_current_user)):
    if current_user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(request, "auth/login.html", {"next": safe_internal_path(next)})


@router.post("/login")
def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/dashboard"),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "auth/login.html",
            {"error": "Invalid email or password", "email": email, "next": safe_internal_path(next)},
        )
    token = create_session(user.id, db)
    response = RedirectResponse(safe_internal_path(next), status_code=302)
    set_session_cookie(response, token)
    return response


@router.get("/register")
def register_page(request: Request, current_user=Depends(get_current_user)):
    if current_user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(request, "auth/register.html", {})


@router.post("/register")
def register_post(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            request, "auth/register.html",
            {"error": "An account with that email already exists.", "email": email, "display_name": display_name},
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            request, "auth/register.html",
            {"error": "Password must be at least 8 characters.", "email": email, "display_name": display_name},
        )
    user = User(email=email, display_name=display_name.strip(), password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_session(user.id, db)
    response = RedirectResponse("/dashboard", status_code=302)
    set_session_cookie(response, token)
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("session")
    if token:
        db.query(UserSession).filter(UserSession.token == token).delete()
        db.commit()
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie("session")
    return response
