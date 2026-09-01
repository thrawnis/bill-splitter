import uuid
from decimal import Decimal, InvalidOperation

from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..models import GroupMember, User

templates = Jinja2Templates(directory="app/templates")


def is_group_member(db: Session, group_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
        .first()
        is not None
    )


def get_group_member_users(db: Session, group_id: uuid.UUID) -> list[User]:
    return (
        db.query(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .filter(GroupMember.group_id == group_id)
        .all()
    )


def parse_money(value: str) -> Decimal | None:
    try:
        amount = Decimal(value.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None
    if amount < 0 or amount > Decimal("999999.99"):
        return None
    return amount.quantize(Decimal("0.01"))
