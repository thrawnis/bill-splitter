from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, selectinload

from ..auth import require_user
from ..database import get_db
from ..models import Bill, Group, GroupMember, User
from ..services.balance import calculate_group_balances
from .common import templates

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(request: Request, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    group_ids = [
        m.group_id
        for m in db.query(GroupMember).filter(GroupMember.user_id == current_user.id).all()
    ]
    groups = (
        db.query(Group)
        .options(selectinload(Group.members))
        .filter(Group.id.in_(group_ids))
        .all()
        if group_ids
        else []
    )

    total_owed = Decimal("0")
    total_owed_to_me = Decimal("0")

    for group in groups:
        for (debtor, creditor), amount in calculate_group_balances(group.id, db).items():
            if debtor == current_user.id:
                total_owed += amount
            elif creditor == current_user.id:
                total_owed_to_me += amount

    recent_bills = (
        db.query(Bill)
        .filter(Bill.group_id.in_(group_ids))
        .order_by(Bill.created_at.desc())
        .limit(10)
        .all()
        if group_ids
        else []
    )

    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            "current_user": current_user,
            "groups": groups,
            "total_owed": total_owed,
            "total_owed_to_me": total_owed_to_me,
            "recent_bills": recent_bills,
        },
    )
