from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import create_session, get_current_user, hash_password, set_session_cookie, verify_password
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
async def login_page(request: Request, next: str = "/dashboard", current_user=Depends(get_current_user)):
    if current_user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("auth/login.html", {"request": request, "next": next})


@router.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/dashboard"),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Invalid email or password", "email": email, "next": next},
        )
    token = create_session(user.id, db)
    response = RedirectResponse(next if next.startswith("/") else "/dashboard", status_code=302)
    set_session_cookie(response, token)
    return response


@router.get("/register")
async def register_page(request: Request, current_user=Depends(get_current_user)):
    if current_user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("auth/register.html", {"request": request})


@router.post("/register")
async def register_post(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "An account with that email already exists.", "email": email, "display_name": display_name},
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "Password must be at least 8 characters.", "email": email, "display_name": display_name},
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
async def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("session")
    if token:
        from ..models import UserSession
        db.query(UserSession).filter(UserSession.token == token).delete()
        db.commit()
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie("session")
    return response
