import secrets
import uuid
from decimal import Decimal
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import require_user
from ..config import settings
from ..database import get_db
from ..models import Bill, BillItem, Group, GroupMember, ItemAssignment, Settlement, User
from ..services.balance import bill_person_totals
from ..services.ollama import parse_receipt

router = APIRouter(tags=["bills"])
templates = Jinja2Templates(directory="app/templates")

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


def _get_group_members(group_id, db: Session) -> list[User]:
    ids = [m.user_id for m in db.query(GroupMember).filter(GroupMember.group_id == group_id).all()]
    return db.query(User).filter(User.id.in_(ids)).all() if ids else []


def _bill_context(bill: Bill, current_user: User, db: Session) -> dict:
    members = _get_group_members(bill.group_id, db)
    person_totals = bill_person_totals(bill, members)
    payer = db.query(User).filter(User.id == bill.paid_by).first()
    return {
        "bill": bill,
        "members": members,
        "person_totals": person_totals,
        "payer": payer,
        "current_user": current_user,
    }


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


@router.get("/groups/{group_id}/bills/new")
async def new_bill_page(
    group_id,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        return RedirectResponse("/groups", status_code=302)
    if not db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == current_user.id).first():
        return RedirectResponse("/groups", status_code=302)

    members = _get_group_members(group_id, db)
    return templates.TemplateResponse(
        "bills/new.html",
        {"request": request, "current_user": current_user, "group": group, "members": members},
    )


@router.post("/groups/{group_id}/bills")
async def create_bill(
    group_id,
    request: Request,
    title: str = Form(...),
    paid_by: str = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == current_user.id).first():
        return RedirectResponse("/groups", status_code=302)

    bill = Bill(
        group_id=group_id,
        title=title.strip(),
        paid_by=uuid.UUID(paid_by),
        created_by=current_user.id,
        share_token=secrets.token_urlsafe(32),
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return RedirectResponse(f"/bills/{bill.id}", status_code=302)


@router.get("/bills/{bill_id}")
async def bill_detail(
    bill_id,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        return RedirectResponse("/dashboard", status_code=302)
    if not db.query(GroupMember).filter(GroupMember.group_id == bill.group_id, GroupMember.user_id == current_user.id).first():
        return RedirectResponse("/dashboard", status_code=302)

    ctx = _bill_context(bill, current_user, db)
    ctx["request"] = request
    return templates.TemplateResponse("bills/detail.html", ctx)


@router.post("/bills/{bill_id}/items")
async def add_item(
    bill_id,
    request: Request,
    name: str = Form(...),
    price: str = Form(...),
    quantity: int = Form(default=1),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill or not db.query(GroupMember).filter(GroupMember.group_id == bill.group_id, GroupMember.user_id == current_user.id).first():
        return RedirectResponse("/dashboard", status_code=302)

    try:
        price_dec = Decimal(price.replace(",", "."))
        if price_dec <= 0:
            raise ValueError
    except Exception:
        if _is_htmx(request):
            ctx = _bill_context(bill, current_user, db)
            ctx.update({"request": request, "item_error": "Invalid price."})
            return templates.TemplateResponse("partials/bill_content.html", ctx)
        return RedirectResponse(f"/bills/{bill_id}", status_code=302)

    db.add(BillItem(bill_id=bill_id, name=name.strip(), price=price_dec, quantity=max(1, quantity)))
    db.commit()
    db.refresh(bill)

    ctx = _bill_context(bill, current_user, db)
    ctx["request"] = request
    return templates.TemplateResponse("partials/bill_content.html", ctx)


@router.delete("/bills/{bill_id}/items/{item_id}")
async def delete_item(
    bill_id,
    item_id,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill or not db.query(GroupMember).filter(GroupMember.group_id == bill.group_id, GroupMember.user_id == current_user.id).first():
        return RedirectResponse("/dashboard", status_code=302)

    item = db.query(BillItem).filter(BillItem.id == item_id, BillItem.bill_id == bill_id).first()
    if item:
        db.delete(item)
        db.commit()

    db.refresh(bill)
    ctx = _bill_context(bill, current_user, db)
    ctx["request"] = request
    return templates.TemplateResponse("partials/bill_content.html", ctx)


@router.post("/bills/{bill_id}/items/{item_id}/toggle/{user_id}")
async def toggle_item_user(
    bill_id,
    item_id,
    user_id,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill or not db.query(GroupMember).filter(GroupMember.group_id == bill.group_id, GroupMember.user_id == current_user.id).first():
        return RedirectResponse("/dashboard", status_code=302)

    item = db.query(BillItem).filter(BillItem.id == item_id, BillItem.bill_id == bill_id).first()
    if not item:
        return RedirectResponse(f"/bills/{bill_id}", status_code=302)

    existing = db.query(ItemAssignment).filter(ItemAssignment.item_id == item_id, ItemAssignment.user_id == user_id).first()
    if existing:
        db.delete(existing)
    else:
        db.add(ItemAssignment(item_id=item_id, user_id=uuid.UUID(str(user_id)), share=Decimal("1")))

    db.flush()

    # Recalculate equal shares
    assignments = db.query(ItemAssignment).filter(ItemAssignment.item_id == item_id).all()
    if assignments:
        equal_share = Decimal("1") / len(assignments)
        for a in assignments:
            a.share = equal_share

    db.commit()
    db.refresh(bill)

    ctx = _bill_context(bill, current_user, db)
    ctx["request"] = request
    return templates.TemplateResponse("partials/bill_content.html", ctx)


@router.post("/bills/{bill_id}/tax-tip")
async def update_tax_tip(
    bill_id,
    request: Request,
    tax: str = Form(default="0"),
    tip: str = Form(default="0"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill or not db.query(GroupMember).filter(GroupMember.group_id == bill.group_id, GroupMember.user_id == current_user.id).first():
        return RedirectResponse("/dashboard", status_code=302)

    try:
        bill.tax = max(Decimal("0"), Decimal(tax.replace(",", ".") or "0"))
        bill.tip = max(Decimal("0"), Decimal(tip.replace(",", ".") or "0"))
        db.commit()
        db.refresh(bill)
    except Exception:
        pass

    ctx = _bill_context(bill, current_user, db)
    ctx["request"] = request
    return templates.TemplateResponse("partials/bill_content.html", ctx)


@router.post("/bills/{bill_id}/scan")
async def scan_receipt(
    bill_id,
    request: Request,
    image: UploadFile = File(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill or not db.query(GroupMember).filter(GroupMember.group_id == bill.group_id, GroupMember.user_id == current_user.id).first():
        return templates.TemplateResponse(
            "partials/scan_results.html",
            {"request": request, "error": "Access denied.", "bill_id": bill_id},
        )

    if image.content_type not in ALLOWED_IMAGE_TYPES:
        return templates.TemplateResponse(
            "partials/scan_results.html",
            {"request": request, "error": "Please upload a JPEG, PNG, or WebP image.", "bill_id": bill_id},
        )

    upload_path = Path(settings.upload_dir) / f"{bill_id}_{secrets.token_hex(8)}.jpg"
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(upload_path, "wb") as f:
        await f.write(await image.read())

    # Store receipt image path on bill
    bill.receipt_image_path = str(upload_path)
    db.commit()

    try:
        items = await parse_receipt(str(upload_path))
    except Exception as e:
        return templates.TemplateResponse(
            "partials/scan_results.html",
            {"request": request, "error": f"Ollama error: {e}", "bill_id": bill_id},
        )

    return templates.TemplateResponse(
        "partials/scan_results.html",
        {"request": request, "items": items, "bill_id": str(bill_id)},
    )


@router.get("/bills/share/{share_token}")
async def bill_share(share_token: str, request: Request, db: Session = Depends(get_db)):
    bill = db.query(Bill).filter(Bill.share_token == share_token).first()
    if not bill:
        return templates.TemplateResponse("error.html", {"request": request, "current_user": None, "message": "Bill not found."})

    members = _get_group_members(bill.group_id, db)
    person_totals = bill_person_totals(bill, members)
    payer = db.query(User).filter(User.id == bill.paid_by).first()

    return templates.TemplateResponse(
        "bills/share.html",
        {
            "request": request,
            "current_user": None,
            "bill": bill,
            "members": members,
            "person_totals": person_totals,
            "payer": payer,
        },
    )


@router.post("/groups/{group_id}/settle")
async def record_settlement(
    group_id,
    request: Request,
    to_user_id: str = Form(...),
    amount: str = Form(...),
    note: str = Form(default=""),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == current_user.id).first():
        return RedirectResponse("/groups", status_code=302)

    try:
        amount_dec = Decimal(amount.replace(",", "."))
        if amount_dec <= 0:
            raise ValueError
    except Exception:
        return RedirectResponse(f"/groups/{group_id}", status_code=302)

    db.add(Settlement(
        group_id=group_id,
        from_user_id=current_user.id,
        to_user_id=uuid.UUID(to_user_id),
        amount=amount_dec,
        note=note.strip() or None,
    ))
    db.commit()
    return RedirectResponse(f"/groups/{group_id}", status_code=302)
