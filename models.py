"""SQLAlchemy models — Purchasing Management System."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_master: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    users: Mapped[List["AppUser"]] = relationship(back_populates="role")
    permissions: Mapped[List["Permission"]] = relationship(back_populates="role")
    menu_visibility: Mapped[List["MenuVisibility"]] = relationship(back_populates="role")


class StudentList(Base):
    __tablename__ = "student_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    student_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[Optional["AppUser"]] = relationship(back_populates="student", uselist=False)


class AppUser(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_list_id: Mapped[int] = mapped_column(ForeignKey("student_list.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(200), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    student: Mapped["StudentList"] = relationship(back_populates="user")
    role: Mapped["Role"] = relationship(back_populates="users")
    purchase_requests: Mapped[List["PurchaseRequest"]] = relationship(
        back_populates="requester", foreign_keys="PurchaseRequest.requester_id"
    )
    purchase_orders: Mapped[List["PurchaseOrder"]] = relationship(back_populates="purchasing_user")
    team_memberships: Mapped[List["TeamMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    pr_status_changes: Mapped[List["PRStatusHistory"]] = relationship(
        back_populates="changed_by", foreign_keys="PRStatusHistory.changed_by_id"
    )
    ir_status_changes: Mapped[List["IRStatusHistory"]] = relationship(
        back_populates="changed_by", foreign_keys="IRStatusHistory.changed_by_id"
    )
    rn_status_changes: Mapped[List["RNStatusHistory"]] = relationship(
        back_populates="changed_by", foreign_keys="RNStatusHistory.changed_by_id"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String(80), nullable=False)
    field_name: Mapped[str] = mapped_column(String(80), nullable=False)
    can_view: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    role: Mapped["Role"] = relationship(back_populates="permissions")


class MenuVisibility(Base):
    __tablename__ = "menu_visibility"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    menu_key: Mapped[str] = mapped_column(String(80), nullable=False)
    can_view: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    show_own_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    role: Mapped["Role"] = relationship(back_populates="menu_visibility")


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(80))
    email: Mapped[Optional[str]] = mapped_column(String(200))
    address: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    line_items: Mapped[List["PurchaseRequestItem"]] = relationship(back_populates="supplier")


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    class_name: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(40), nullable=False)
    budget_amount: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    teams: Mapped[List["Team"]] = relationship(back_populates="class_")
    purchasing_rounds: Mapped[List["PurchasingRound"]] = relationship(back_populates="class_")
    purchase_requests: Mapped[List["PurchaseRequest"]] = relationship(back_populates="class_")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_code: Mapped[str] = mapped_column(String(40), nullable=False)
    team_name: Mapped[str] = mapped_column(String(200), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    team_budget_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    class_: Mapped["Class"] = relationship(back_populates="teams")
    purchase_requests: Mapped[List["PurchaseRequest"]] = relationship(back_populates="team")
    memberships: Mapped[List["TeamMembership"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )


class TeamMembership(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("user_id", "team_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["AppUser"] = relationship(back_populates="team_memberships")
    team: Mapped["Team"] = relationship(back_populates="memberships")


class PurchasingRound(Base):
    __tablename__ = "purchasing_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_name: Mapped[str] = mapped_column(String(120), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    class_: Mapped["Class"] = relationship(back_populates="purchasing_rounds")
    purchase_requests: Mapped[List["PurchaseRequest"]] = relationship(
        back_populates="purchasing_round"
    )


class DocumentNumbering(Base):
    __tablename__ = "document_numbering"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_type: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pad_length: Mapped[int] = mapped_column(Integer, default=5, nullable=False)


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pr_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    purchasing_round_id: Mapped[int] = mapped_column(ForeignKey("purchasing_rounds.id"), nullable=False)
    budget_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    requester: Mapped["AppUser"] = relationship(
        back_populates="purchase_requests", foreign_keys=[requester_id]
    )
    class_: Mapped["Class"] = relationship(back_populates="purchase_requests")
    team: Mapped["Team"] = relationship(back_populates="purchase_requests")
    purchasing_round: Mapped["PurchasingRound"] = relationship(back_populates="purchase_requests")
    items: Mapped[List["PurchaseRequestItem"]] = relationship(
        back_populates="purchase_request", cascade="all, delete-orphan"
    )
    purchase_orders: Mapped[List["PurchaseOrder"]] = relationship(back_populates="purchase_request")
    status_history: Mapped[List["PRStatusHistory"]] = relationship(
        back_populates="purchase_request", cascade="all, delete-orphan"
    )


class PRStatusHistory(Base):
    __tablename__ = "pr_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("purchase_requests.id"), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(80))
    to_status: Mapped[str] = mapped_column(String(80), nullable=False)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    purchase_request: Mapped["PurchaseRequest"] = relationship(back_populates="status_history")
    changed_by: Mapped["AppUser"] = relationship(
        back_populates="pr_status_changes", foreign_keys=[changed_by_id]
    )


class PurchaseRequestItem(Base):
    __tablename__ = "purchase_request_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("purchase_requests.id"), nullable=False)
    item_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    sub_total: Mapped[float] = mapped_column(Float, nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    link: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approver_decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    hop_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    purchase_request: Mapped["PurchaseRequest"] = relationship(back_populates="items")
    supplier: Mapped["Supplier"] = relationship(back_populates="line_items")
    line_purchase_orders: Mapped[List["PurchaseOrder"]] = relationship(back_populates="pr_line_item")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    pr_id: Mapped[int] = mapped_column(ForeignKey("purchase_requests.id"), nullable=False)
    pr_line_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("purchase_request_items.id"), nullable=True)
    purchasing_team_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    purchase_request: Mapped["PurchaseRequest"] = relationship(back_populates="purchase_orders")
    pr_line_item: Mapped[Optional["PurchaseRequestItem"]] = relationship(
        back_populates="line_purchase_orders",
        foreign_keys=[pr_line_item_id],
    )
    purchasing_user: Mapped["AppUser"] = relationship(back_populates="purchase_orders")
    inventory_receives: Mapped[List["InventoryReceive"]] = relationship(back_populates="purchase_order")


class InventoryReceive(Base):
    __tablename__ = "inventory_receive"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ir_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    received_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    po_document_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    delivery_note_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invoice_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_supplier_resolution: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pickup_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requester_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    requester_accepted_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="inventory_receives")
    requester_acceptor: Mapped[Optional["AppUser"]] = relationship(foreign_keys=[requester_accepted_by_id])
    return_notes: Mapped[List["ReturnNote"]] = relationship(back_populates="inventory_receive")
    attachments: Mapped[List["IRAttachment"]] = relationship(
        back_populates="inventory_receive",
        cascade="all, delete-orphan",
    )
    status_history: Mapped[List["IRStatusHistory"]] = relationship(
        back_populates="inventory_receive", cascade="all, delete-orphan"
    )


class IRAttachment(Base):
    __tablename__ = "ir_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ir_id: Mapped[int] = mapped_column(ForeignKey("inventory_receive.id"), nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    inventory_receive: Mapped["InventoryReceive"] = relationship(back_populates="attachments")
    uploaded_by: Mapped["AppUser"] = relationship()


class ReturnNote(Base):
    __tablename__ = "return_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rn_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    ir_id: Mapped[int] = mapped_column(ForeignKey("inventory_receive.id"), nullable=False)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="draft", nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    product_dropped_off: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    inventory_receive: Mapped["InventoryReceive"] = relationship(back_populates="return_notes")
    status_history: Mapped[List["RNStatusHistory"]] = relationship(
        back_populates="return_note", cascade="all, delete-orphan"
    )


class IRStatusHistory(Base):
    __tablename__ = "ir_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ir_id: Mapped[int] = mapped_column(ForeignKey("inventory_receive.id"), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(80))
    to_status: Mapped[str] = mapped_column(String(80), nullable=False)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    inventory_receive: Mapped["InventoryReceive"] = relationship(back_populates="status_history")
    changed_by: Mapped["AppUser"] = relationship(
        back_populates="ir_status_changes", foreign_keys=[changed_by_id]
    )


class RNStatusHistory(Base):
    __tablename__ = "rn_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rn_id: Mapped[int] = mapped_column(ForeignKey("return_notes.id"), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(80))
    to_status: Mapped[str] = mapped_column(String(80), nullable=False)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    return_note: Mapped["ReturnNote"] = relationship(back_populates="status_history")
    changed_by: Mapped["AppUser"] = relationship(
        back_populates="rn_status_changes", foreign_keys=[changed_by_id]
    )


class BudgetTransaction(Base):
    __tablename__ = "budget_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    reference_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_type: Mapped[str] = mapped_column(String(10), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FieldRule(Base):
    __tablename__ = "field_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(80), nullable=False)
    field_name: Mapped[str] = mapped_column(String(80), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    rule_value: Mapped[str] = mapped_column(String(200), nullable=False)
    error_message: Mapped[str] = mapped_column(String(500), nullable=False)


class FieldLockConfig(Base):
    __tablename__ = "field_lock_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_type: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[str] = mapped_column(String(80), nullable=False)
    table_name: Mapped[str] = mapped_column(String(80), nullable=False)
    field_name: Mapped[str] = mapped_column(String(80), nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DocumentStatus(Base):
    __tablename__ = "document_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_type: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status_label: Mapped[str] = mapped_column(String(120), nullable=False)
    status_color: Mapped[str] = mapped_column(String(40), nullable=False)
    order_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("document_type", "status_code"),)


class StatusActionPermission(Base):
    __tablename__ = "status_action_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_type: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[str] = mapped_column(String(80), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    action_key: Mapped[str] = mapped_column(String(40), nullable=False)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    button_label: Mapped[str] = mapped_column(String(120), nullable=False)
    next_status: Mapped[Optional[str]] = mapped_column(String(80))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_type: Mapped[str] = mapped_column(String(10), nullable=False)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
