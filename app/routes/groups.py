import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import Group, GroupMember, User
from ..services.balance import calculate_group_balances

router = APIRouter(prefix="/groups", tags=["groups"])
templates = Jinja2Templates(directory="app/templates")


def _member_users(group: Group, db: Session) -> list[User]:
    user_ids = [m.user_id for m in group.members]
    return db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []


@router.get("")
async def list_groups(request: Request, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    memberships = db.query(GroupMember).filter(GroupMember.user_id == current_user.id).all()
    group_ids = [m.group_id for m in memberships]
    groups = db.query(Group).filter(Group.id.in_(group_ids)).order_by(Group.created_at.desc()).all() if group_ids else []
    return templates.TemplateResponse(request, "groups/list.html", {"request": request, "current_user": current_user, "groups": groups})


@router.get("/new")
async def new_group_page(request: Request, current_user: User = Depends(require_user)):
    return templates.TemplateResponse(request, "groups/new.html", {"request": request, "current_user": current_user})


@router.post("")
async def create_group(
    request: Request,
    name: str = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not name.strip():
        return templates.TemplateResponse(request, "groups/new.html", {"request": request, "current_user": current_user, "error": "Group name is required."})

    group = Group(name=name.strip(), created_by=current_user.id, invite_token=secrets.token_urlsafe(32))
    db.add(group)
    db.flush()
    db.add(GroupMember(group_id=group.id, user_id=current_user.id, role="owner"))
    db.commit()
    return RedirectResponse(f"/groups/{group.id}", status_code=302)


@router.get("/{group_id}")
async def group_detail(
    group_id,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        return RedirectResponse("/groups", status_code=302)

    membership = db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == current_user.id).first()
    if not membership:
        return RedirectResponse("/groups", status_code=302)

    members = _member_users(group, db)
    balances = calculate_group_balances(group.id, db)
    user_map = {u.id: u for u in members}

    bills = sorted(group.bills, key=lambda b: b.created_at, reverse=True)

    return templates.TemplateResponse(request, "groups/detail.html",
        {
            "request": request,
            "current_user": current_user,
            "group": group,
            "members": members,
            "user_map": user_map,
            "balances": balances,
            "bills": bills,
            "membership": membership,
        },
    )


@router.get("/join/{token}")
async def join_group_page(token: str, request: Request, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    group = db.query(Group).filter(Group.invite_token == token).first()
    if not group:
        return templates.TemplateResponse(request, "error.html", {"request": request, "current_user": current_user, "message": "Invite link is invalid or expired."})

    already_member = db.query(GroupMember).filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id).first()
    if already_member:
        return RedirectResponse(f"/groups/{group.id}", status_code=302)

    return templates.TemplateResponse(request, "groups/join.html", {"request": request, "current_user": current_user, "group": group, "token": token})


@router.post("/join/{token}")
async def join_group(token: str, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    group = db.query(Group).filter(Group.invite_token == token).first()
    if not group:
        return RedirectResponse("/groups", status_code=302)

    already = db.query(GroupMember).filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id).first()
    if not already:
        db.add(GroupMember(group_id=group.id, user_id=current_user.id, role="member"))
        db.commit()

    return RedirectResponse(f"/groups/{group.id}", status_code=302)
