from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session, selectinload

from ..models import Bill, BillItem, Settlement

CENT = Decimal("0.01")


def _bills_with_items(group_id: UUID, db: Session) -> list[Bill]:
    return (
        db.query(Bill)
        .options(selectinload(Bill.items).selectinload(BillItem.assignments))
        .filter(Bill.group_id == group_id)
        .all()
    )


def _user_subtotals(bill: Bill) -> dict[UUID, Decimal]:
    subtotals: dict[UUID, Decimal] = {}
    for item in bill.items:
        item_total = item.price * item.quantity
        for assignment in item.assignments:
            uid = assignment.user_id
            subtotals[uid] = subtotals.get(uid, Decimal("0")) + item_total * assignment.share
    return subtotals


def calculate_group_balances(group_id: UUID, db: Session) -> dict[tuple[UUID, UUID], Decimal]:
    """
    Returns {(debtor_id, creditor_id): amount} where amount > 0.
    Already simplified: net bidirectional debts, settlements applied.
    """
    raw: dict[tuple[UUID, UUID], Decimal] = {}

    for bill in _bills_with_items(group_id, db):
        subtotals = _user_subtotals(bill)
        grand_subtotal = sum(subtotals.values())

        for uid, subtotal in subtotals.items():
            if uid == bill.paid_by:
                continue
            extra = (subtotal / grand_subtotal) * (bill.tax + bill.tip) if grand_subtotal else Decimal("0")
            key = (uid, bill.paid_by)
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
            simplified[(debtor, creditor)] = net.quantize(CENT)
        elif net < Decimal("-0.005"):
            simplified[(creditor, debtor)] = (-net).quantize(CENT)

    return simplified


def bill_person_totals(bill: Bill, members) -> dict[UUID, Decimal]:
    """
    Per-person total for a bill including proportional tax/tip, rounded to
    cents such that the parts always sum to the exact bill total — any
    rounding remainder lands on the payer (or the largest share).
    """
    totals = {m.id: Decimal("0") for m in members}
    totals.update(_user_subtotals(bill))

    grand_subtotal = sum(totals.values())
    if grand_subtotal > 0 and (bill.tax + bill.tip) > 0:
        for uid in totals:
            totals[uid] += (totals[uid] / grand_subtotal) * (bill.tax + bill.tip)

    quantized = {uid: v.quantize(CENT) for uid, v in totals.items()}

    if grand_subtotal > 0:
        exact_total = (grand_subtotal + bill.tax + bill.tip).quantize(CENT)
        remainder = exact_total - sum(quantized.values())
        if remainder:
            target = bill.paid_by if quantized.get(bill.paid_by) else max(quantized, key=lambda u: quantized[u])
            quantized[target] += remainder

    return quantized
