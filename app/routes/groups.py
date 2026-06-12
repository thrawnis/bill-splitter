import secrets
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload

from ..auth import require_user
from ..database import get_db
from ..models import Bill, Group, GroupMember, User
from ..services.balance import calculate_group_balances
from .common import get_group_member_users, is_group_member, templates

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("")
def list_groups(request: Request, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    group_ids = [
        m.group_id
        for m in db.query(GroupMember).filter(GroupMember.user_id == current_user.id).all()
    ]
    groups = (
        db.query(Group)
        .options(selectinload(Group.members), selectinload(Group.bills))
        .filter(Group.id.in_(group_ids))
        .order_by(Group.created_at.desc())
        .all()
        if group_ids
        else []
    )
    return templates.TemplateResponse(request, "groups/list.html", {"current_user": current_user, "groups": groups})


@router.get("/new")
def new_group_page(request: Request, current_user: User = Depends(require_user)):
    return templates.TemplateResponse(request, "groups/new.html", {"current_user": current_user})


@router.post("")
def create_group(
    request: Request,
    name: str = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not name.strip():
        return templates.TemplateResponse(request, "groups/new.html", {"current_user": current_user, "error": "Group name is required."})

    group = Group(name=name.strip(), created_by=current_user.id, invite_token=secrets.token_urlsafe(32))
    db.add(group)
    db.flush()
    db.add(GroupMember(group_id=group.id, user_id=current_user.id, role="owner"))
    db.commit()
    return RedirectResponse(f"/groups/{group.id}", status_code=302)


@router.get("/join/{token}")
def join_group_page(token: str, request: Request, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    group = db.query(Group).filter(Group.invite_token == token).first()
    if not group:
        return templates.TemplateResponse(request, "error.html", {"current_user": current_user, "message": "Invite link is invalid or expired."})

    if is_group_member(db, group.id, current_user.id):
        return RedirectResponse(f"/groups/{group.id}", status_code=302)

    return templates.TemplateResponse(request, "groups/join.html", {"current_user": current_user, "group": group, "token": token})


@router.post("/join/{token}")
def join_group(token: str, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    group = db.query(Group).filter(Group.invite_token == token).first()
    if not group:
        return RedirectResponse("/groups", status_code=302)

    if not is_group_member(db, group.id, current_user.id):
        db.add(GroupMember(group_id=group.id, user_id=current_user.id, role="member"))
        db.commit()

    return RedirectResponse(f"/groups/{group.id}", status_code=302)


@router.get("/{group_id}")
def group_detail(
    group_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    group = (
        db.query(Group)
        .options(selectinload(Group.bills).selectinload(Bill.payer))
        .filter(Group.id == group_id)
        .first()
    )
    if not group or not is_group_member(db, group_id, current_user.id):
        return RedirectResponse("/groups", status_code=302)

    members = get_group_member_users(db, group_id)
    balances = calculate_group_balances(group.id, db)
    user_map = {u.id: u for u in members}
    bills = sorted(group.bills, key=lambda b: b.created_at, reverse=True)

    return templates.TemplateResponse(
        request, "groups/detail.html",
        {
            "current_user": current_user,
            "group": group,
            "members": members,
            "user_map": user_map,
            "balances": balances,
            "bills": bills,
        },
    )
