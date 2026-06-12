from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..auth import hash_password, require_user, verify_password
from ..database import get_db
from ..models import User
from .common import templates

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
def profile_page(request: Request, current_user: User = Depends(require_user)):
    return templates.TemplateResponse(request, "profile.html", {"current_user": current_user})


@router.post("")
def update_profile(
    request: Request,
    display_name: str = Form(...),
    venmo_handle: str = Form(default=""),
    paypal_me: str = Form(default=""),
    zelle_contact: str = Form(default=""),
    cashapp_handle: str = Form(default=""),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not display_name.strip():
        return templates.TemplateResponse(
            request, "profile.html",
            {"current_user": current_user, "error": "Display name cannot be empty."},
        )

    current_user.display_name = display_name.strip()[:100]
    current_user.venmo_handle = venmo_handle.strip().lstrip("@")[:100] or None
    current_user.paypal_me = paypal_me.strip().lstrip("/")[:100] or None
    current_user.zelle_contact = zelle_contact.strip()[:150] or None
    current_user.cashapp_handle = cashapp_handle.strip().lstrip("$")[:100] or None
    db.commit()

    return templates.TemplateResponse(
        request, "profile.html",
        {"current_user": current_user, "success": "Profile updated."},
    )


@router.post("/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not verify_password(current_password, current_user.password_hash):
        return templates.TemplateResponse(
            request, "profile.html",
            {"current_user": current_user, "pw_error": "Current password is incorrect."},
        )
    if len(new_password) < 8:
        return templates.TemplateResponse(
            request, "profile.html",
            {"current_user": current_user, "pw_error": "New password must be at least 8 characters."},
        )
    current_user.password_hash = hash_password(new_password)
    db.commit()
    return templates.TemplateResponse(
        request, "profile.html",
        {"current_user": current_user, "pw_success": "Password changed."},
    )
