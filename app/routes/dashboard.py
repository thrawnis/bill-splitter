from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import Bill, Group, GroupMember, User
from ..services.balance import calculate_group_balances

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard")
async def dashboard(request: Request, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    memberships = (
        db.query(GroupMember)
        .filter(GroupMember.user_id == current_user.id)
        .all()
    )
    group_ids = [m.group_id for m in memberships]
    groups = db.query(Group).filter(Group.id.in_(group_ids)).all() if group_ids else []

    total_owed = Decimal("0")
    total_owed_to_me = Decimal("0")

    for group in groups:
        balances = calculate_group_balances(group.id, db)
        for (debtor, creditor), amount in balances.items():
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

    return templates.TemplateResponse(request, "dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "groups": groups,
            "total_owed": total_owed,
            "total_owed_to_me": total_owed_to_me,
            "recent_bills": recent_bills,
        },
    )
