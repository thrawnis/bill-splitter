import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    venmo_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    paypal_me: Mapped[str | None] = mapped_column(String(100), nullable=True)
    zelle_contact: Mapped[str | None] = mapped_column(String(150), nullable=True)
    cashapp_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    group_memberships: Mapped[list["GroupMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(back_populates="sessions")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    invite_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list["GroupMember"]] = relationship(back_populates="group", cascade="all, delete-orphan")
    bills: Mapped[list["Bill"]] = relationship(back_populates="group", cascade="all, delete-orphan")
    settlements: Mapped[list["Settlement"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    group: Mapped["Group"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="group_memberships")


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tax: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    tip: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    paid_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    share_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    group: Mapped["Group"] = relationship(back_populates="bills")
    items: Mapped[list["BillItem"]] = relationship(back_populates="bill", cascade="all, delete-orphan", order_by="BillItem.created_at")
    guests: Mapped[list["BillGuest"]] = relationship(back_populates="bill", cascade="all, delete-orphan", order_by="BillGuest.created_at")
    payer: Mapped["User"] = relationship(foreign_keys=[paid_by])
    creator: Mapped["User"] = relationship(foreign_keys=[created_by])


class BillItem(Base):
    __tablename__ = "bill_items"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    bill: Mapped["Bill"] = relationship(back_populates="items")
    assignments: Mapped[list["ItemAssignment"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class ItemAssignment(Base):
    __tablename__ = "item_assignments"
    __table_args__ = (UniqueConstraint("item_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("bill_items.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    guest_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("bill_guests.id", ondelete="CASCADE"), nullable=True)
    share: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)

    item: Mapped["BillItem"] = relationship(back_populates="assignments")
    user: Mapped["User | None"] = relationship()
    guest: Mapped["BillGuest | None"] = relationship()

    @property
    def participant_key(self) -> tuple[str, uuid.UUID]:
        return ("u", self.user_id) if self.user_id else ("g", self.guest_id)


class BillGuest(Base):
    __tablename__ = "bill_guests"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    bill: Mapped["Bill"] = relationship(back_populates="guests")


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    from_user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    group: Mapped["Group"] = relationship(back_populates="settlements")
    from_user: Mapped["User"] = relationship(foreign_keys=[from_user_id])
    to_user: Mapped["User"] = relationship(foreign_keys=[to_user_id])
