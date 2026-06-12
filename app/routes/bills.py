import secrets
import uuid
from decimal import Decimal
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import require_user
from ..config import settings
from ..database import get_db
from ..models import Bill, BillItem, Group, ItemAssignment, Settlement, User
from ..services.balance import bill_person_totals
from ..services.ollama import parse_receipt
from .common import get_group_member_users, is_group_member, parse_money, templates

router = APIRouter(tags=["bills"])

UPLOAD_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _get_bill_for_member(bill_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> Bill | None:
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill or not is_group_member(db, bill.group_id, user_id):
        return None
    return bill


def _bill_context(bill: Bill, current_user: User, db: Session, **extra) -> dict:
    members = get_group_member_users(db, bill.group_id)
    return {
        "bill": bill,
        "members": members,
        "person_totals": bill_person_totals(bill, members),
        "payer": db.query(User).filter(User.id == bill.paid_by).first(),
        "current_user": current_user,
        **extra,
    }


def _bill_partial(request: Request, bill: Bill, current_user: User, db: Session, **extra):
    return templates.TemplateResponse(
        request, "partials/bill_content.html", _bill_context(bill, current_user, db, **extra)
    )


@router.get("/groups/{group_id}/bills/new")
def new_bill_page(
    group_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group or not is_group_member(db, group_id, current_user.id):
        return RedirectResponse("/groups", status_code=302)

    members = get_group_member_users(db, group_id)
    return templates.TemplateResponse(
        request, "bills/new.html",
        {"current_user": current_user, "group": group, "members": members},
    )


@router.post("/groups/{group_id}/bills")
def create_bill(
    group_id: uuid.UUID,
    title: str = Form(...),
    paid_by: uuid.UUID = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not is_group_member(db, group_id, current_user.id) or not is_group_member(db, group_id, paid_by):
        return RedirectResponse("/groups", status_code=302)

    bill = Bill(
        group_id=group_id,
        title=title.strip(),
        paid_by=paid_by,
        created_by=current_user.id,
        share_token=secrets.token_urlsafe(32),
    )
    db.add(bill)
    db.commit()
    return RedirectResponse(f"/bills/{bill.id}", status_code=302)


@router.get("/bills/{bill_id}")
def bill_detail(
    bill_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = _get_bill_for_member(bill_id, current_user.id, db)
    if not bill:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(request, "bills/detail.html", _bill_context(bill, current_user, db))


@router.post("/bills/{bill_id}/items")
def add_item(
    bill_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    price: str = Form(...),
    quantity: int = Form(default=1),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = _get_bill_for_member(bill_id, current_user.id, db)
    if not bill:
        return RedirectResponse("/dashboard", status_code=302)

    price_dec = parse_money(price)
    if not price_dec or not name.strip():
        return _bill_partial(request, bill, current_user, db, item_error="Enter a valid name and price.")

    db.add(BillItem(bill_id=bill_id, name=name.strip()[:200], price=price_dec, quantity=max(1, quantity)))
    db.commit()
    db.refresh(bill)
    return _bill_partial(request, bill, current_user, db)


@router.delete("/bills/{bill_id}/items/{item_id}")
def delete_item(
    bill_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = _get_bill_for_member(bill_id, current_user.id, db)
    if not bill:
        return RedirectResponse("/dashboard", status_code=302)

    item = db.query(BillItem).filter(BillItem.id == item_id, BillItem.bill_id == bill_id).first()
    if item:
        db.delete(item)
        db.commit()
        db.refresh(bill)
    return _bill_partial(request, bill, current_user, db)


@router.post("/bills/{bill_id}/items/{item_id}/toggle/{user_id}")
def toggle_item_user(
    bill_id: uuid.UUID,
    item_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = _get_bill_for_member(bill_id, current_user.id, db)
    if not bill:
        return RedirectResponse("/dashboard", status_code=302)

    item = db.query(BillItem).filter(BillItem.id == item_id, BillItem.bill_id == bill_id).first()
    if not item or not is_group_member(db, bill.group_id, user_id):
        return _bill_partial(request, bill, current_user, db)

    existing = db.query(ItemAssignment).filter(ItemAssignment.item_id == item_id, ItemAssignment.user_id == user_id).first()
    if existing:
        db.delete(existing)
    else:
        db.add(ItemAssignment(item_id=item_id, user_id=user_id, share=Decimal("1")))
    db.flush()

    assignments = db.query(ItemAssignment).filter(ItemAssignment.item_id == item_id).all()
    if assignments:
        equal_share = Decimal("1") / len(assignments)
        for a in assignments:
            a.share = equal_share

    db.commit()
    db.refresh(bill)
    return _bill_partial(request, bill, current_user, db)


@router.post("/bills/{bill_id}/tax-tip")
def update_tax_tip(
    bill_id: uuid.UUID,
    request: Request,
    tax: str = Form(default="0"),
    tip: str = Form(default="0"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = _get_bill_for_member(bill_id, current_user.id, db)
    if not bill:
        return RedirectResponse("/dashboard", status_code=302)

    tax_dec = parse_money(tax or "0")
    tip_dec = parse_money(tip or "0")
    if tax_dec is None or tip_dec is None:
        return _bill_partial(request, bill, current_user, db, item_error="Invalid tax or tip amount.")

    bill.tax = tax_dec
    bill.tip = tip_dec
    db.commit()
    db.refresh(bill)
    return _bill_partial(request, bill, current_user, db)


@router.post("/bills/{bill_id}/scan")
async def scan_receipt(
    bill_id: uuid.UUID,
    request: Request,
    image: UploadFile = File(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    def scan_error(message: str):
        return templates.TemplateResponse(
            request, "partials/scan_results.html", {"error": message, "bill_id": str(bill_id)}
        )

    bill = _get_bill_for_member(bill_id, current_user.id, db)
    if not bill:
        return scan_error("Access denied.")

    extension = UPLOAD_EXTENSIONS.get(image.content_type)
    if not extension:
        return scan_error("Please upload a JPEG, PNG, WebP, or HEIC image.")

    upload_path = Path(settings.upload_dir) / f"{bill_id}_{secrets.token_hex(8)}{extension}"
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    too_large = False
    async with aiofiles.open(upload_path, "wb") as f:
        while chunk := await image.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                too_large = True
                break
            await f.write(chunk)
    if too_large:
        upload_path.unlink(missing_ok=True)
        return scan_error("Image is too large (max 10 MB).")

    bill.receipt_image_path = str(upload_path)
    db.commit()

    try:
        items = await parse_receipt(str(upload_path))
    except Exception:
        return scan_error("Could not reach the AI service. Check that Ollama is running.")

    return templates.TemplateResponse(
        request, "partials/scan_results.html", {"items": items, "bill_id": str(bill_id)}
    )


@router.get("/bills/share/{share_token}")
def bill_share(share_token: str, request: Request, db: Session = Depends(get_db)):
    bill = db.query(Bill).filter(Bill.share_token == share_token).first()
    if not bill:
        return templates.TemplateResponse(request, "error.html", {"current_user": None, "message": "Bill not found."})

    members = get_group_member_users(db, bill.group_id)
    return templates.TemplateResponse(
        request, "bills/share.html",
        {
            "current_user": None,
            "bill": bill,
            "members": members,
            "person_totals": bill_person_totals(bill, members),
            "payer": db.query(User).filter(User.id == bill.paid_by).first(),
        },
    )


@router.post("/groups/{group_id}/settle")
def record_settlement(
    group_id: uuid.UUID,
    to_user_id: uuid.UUID = Form(...),
    amount: str = Form(...),
    note: str = Form(default=""),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not is_group_member(db, group_id, current_user.id) or not is_group_member(db, group_id, to_user_id):
        return RedirectResponse("/groups", status_code=302)

    amount_dec = parse_money(amount)
    if not amount_dec or to_user_id == current_user.id:
        return RedirectResponse(f"/groups/{group_id}", status_code=302)

    db.add(Settlement(
        group_id=group_id,
        from_user_id=current_user.id,
        to_user_id=to_user_id,
        amount=amount_dec,
        note=note.strip()[:500] or None,
    ))
    db.commit()
    return RedirectResponse(f"/groups/{group_id}", status_code=302)
