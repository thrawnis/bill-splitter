from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session, selectinload

from ..models import Bill, BillItem, Settlement

CENT = Decimal("0.01")

# Participant keys are ("u", user_id) for members or ("g", guest_id) for guests.
Participant = tuple[str, UUID]


def _bills_with_items(group_id: UUID, db: Session) -> list[Bill]:
    return (
        db.query(Bill)
        .options(selectinload(Bill.items).selectinload(BillItem.assignments))
        .filter(Bill.group_id == group_id)
        .all()
    )


def _participant_subtotals(bill: Bill) -> dict[Participant, Decimal]:
    subtotals: dict[Participant, Decimal] = {}
    for item in bill.items:
        item_total = item.price * item.quantity
        for assignment in item.assignments:
            key = assignment.participant_key
            subtotals[key] = subtotals.get(key, Decimal("0")) + item_total * assignment.share
    return subtotals


def calculate_group_balances(group_id: UUID, db: Session) -> dict[tuple[UUID, UUID], Decimal]:
    """
    Returns {(debtor_id, creditor_id): amount} where amount > 0, simplified by
    netting bidirectional debts and applying settlements. Only registered
    members participate in running balances; guests are excluded (they pay the
    payer directly), but their shares still count toward tax/tip proportions.
    """
    raw: dict[tuple[UUID, UUID], Decimal] = {}

    for bill in _bills_with_items(group_id, db):
        subtotals = _participant_subtotals(bill)
        grand_subtotal = sum(subtotals.values())

        for (kind, pid), subtotal in subtotals.items():
            if kind != "u" or pid == bill.paid_by:
                continue
            extra = (subtotal / grand_subtotal) * (bill.tax + bill.tip) if grand_subtotal else Decimal("0")
            key = (pid, bill.paid_by)
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


def bill_participant_totals(bill: Bill) -> dict[Participant, Decimal]:
    """
    Per-participant total for a bill including proportional tax/tip, rounded to
    cents so the parts always sum to the exact bill total — any rounding
    remainder lands on the payer (or the largest share). Keyed by participant
    key so members and guests are both represented.
    """
    totals = _participant_subtotals(bill)

    grand_subtotal = sum(totals.values())
    if grand_subtotal > 0 and (bill.tax + bill.tip) > 0:
        for key in totals:
            totals[key] += (totals[key] / grand_subtotal) * (bill.tax + bill.tip)

    quantized = {key: v.quantize(CENT) for key, v in totals.items()}

    if grand_subtotal > 0 and quantized:
        exact_total = (grand_subtotal + bill.tax + bill.tip).quantize(CENT)
        remainder = exact_total - sum(quantized.values())
        if remainder:
            payer_key = ("u", bill.paid_by)
            target = payer_key if quantized.get(payer_key) else max(quantized, key=lambda k: quantized[k])
            quantized[target] += remainder

    return quantized
