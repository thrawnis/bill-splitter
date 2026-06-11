from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from ..models import Bill, Settlement


def calculate_group_balances(group_id: UUID, db: Session) -> dict[tuple[UUID, UUID], Decimal]:
    """
    Returns {(debtor_id, creditor_id): amount} where amount > 0.
    Already simplified: net bidirectional debts, settlements applied.
    """
    raw: dict[tuple[UUID, UUID], Decimal] = {}

    for bill in db.query(Bill).filter(Bill.group_id == group_id).all():
        payer_id = bill.paid_by
        user_subtotals: dict[UUID, Decimal] = {}

        for item in bill.items:
            item_total = item.price * item.quantity
            for assignment in item.assignments:
                uid = assignment.user_id
                user_subtotals[uid] = user_subtotals.get(uid, Decimal("0")) + item_total * assignment.share

        grand_subtotal = sum(user_subtotals.values())

        for uid, subtotal in user_subtotals.items():
            if uid == payer_id:
                continue
            extra = (subtotal / grand_subtotal) * (bill.tax + bill.tip) if grand_subtotal else Decimal("0")
            key = (uid, payer_id)
            raw[key] = raw.get(key, Decimal("0")) + subtotal + extra

    for s in db.query(Settlement).filter(Settlement.group_id == group_id).all():
        key = (s.from_user_id, s.to_user_id)
        raw[key] = raw.get(key, Decimal("0")) - s.amount

    # Net out bidirectional pairs
    simplified: dict[tuple[UUID, UUID], Decimal] = {}
    seen: set[frozenset] = set()

    for (debtor, creditor), amount in raw.items():
        pair = frozenset([debtor, creditor])
        if pair in seen:
            continue
        seen.add(pair)
        reverse = raw.get((creditor, debtor), Decimal("0"))
        net = amount - reverse
        if net > Decimal("0.005"):
            simplified[(debtor, creditor)] = net.quantize(Decimal("0.01"))
        elif net < Decimal("-0.005"):
            simplified[(creditor, debtor)] = (-net).quantize(Decimal("0.01"))

    return simplified


def bill_person_totals(bill, members) -> dict[UUID, Decimal]:
    """Per-person total owed for a bill including proportional tax/tip."""
    totals: dict[UUID, Decimal] = {m.id: Decimal("0") for m in members}

    for item in bill.items:
        item_total = item.price * item.quantity
        for assignment in item.assignments:
            totals[assignment.user_id] = totals.get(assignment.user_id, Decimal("0")) + item_total * assignment.share

    grand_subtotal = sum(totals.values())
    if grand_subtotal > 0 and (bill.tax + bill.tip) > 0:
        for uid in list(totals):
            ratio = totals[uid] / grand_subtotal
            totals[uid] += ratio * (bill.tax + bill.tip)

    return {uid: v.quantize(Decimal("0.01")) for uid, v in totals.items()}
