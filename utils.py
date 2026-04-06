"""Validation, document numbering, and budget / PR helpers."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from models import (
    BudgetTransaction,
    Class,
    DocumentNumbering,
    FieldRule,
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    Team,
)


def generate_document_number(session: Session, document_type: str) -> str:
    """Allocate next document number (alias-friendly name)."""
    return next_document_number(session, document_type)


def next_document_number(session: Session, document_type: str) -> str:
    row = session.query(DocumentNumbering).filter_by(document_type=document_type).first()
    if row is None:
        raise ValueError(f"Unknown document type: {document_type}")
    now_y = datetime.now().year
    if row.year != now_y:
        row.year = now_y
        row.last_number = 0
    row.last_number += 1
    padded = str(row.last_number).zfill(row.pad_length)
    return f"{row.prefix}{row.year}-{padded}"


def recalculate_pr_budget(session: Session, pr_id: int) -> float:
    # Flush so newly added line rows exist in the DB before we query them (otherwise total stays 0).
    session.flush()
    items = session.query(PurchaseRequestItem).filter_by(pr_id=pr_id).all()
    total = sum(float(i.sub_total) for i in items)
    pr = session.get(PurchaseRequest, pr_id)
    if pr:
        pr.budget_amount = total
    return total


def net_budget_reserved_for_class(session: Session, class_id: int) -> float:
    rows = session.query(BudgetTransaction).filter_by(class_id=class_id).all()
    net = 0.0
    for r in rows:
        if r.transaction_type == "consume":
            net += float(r.amount)
        elif r.transaction_type == "return":
            net -= float(r.amount)
    return net


def class_available_budget(session: Session, class_id: int) -> float:
    c = session.get(Class, class_id)
    if not c:
        return 0.0
    return float(c.budget_amount) - net_budget_reserved_for_class(session, class_id)


def has_pr_budget_consume(session: Session, pr_id: int) -> bool:
    return (
        session.query(BudgetTransaction)
        .filter_by(
            reference_id=pr_id,
            reference_type="PR",
            transaction_type="consume",
        )
        .first()
        is not None
    )


def has_pr_budget_return(session: Session, pr_id: int) -> bool:
    return (
        session.query(BudgetTransaction)
        .filter_by(
            reference_id=pr_id,
            reference_type="PR",
            transaction_type="return",
        )
        .first()
        is not None
    )


def record_pr_budget_consume(session: Session, pr: PurchaseRequest) -> None:
    if has_pr_budget_consume(session, pr.id):
        return
    session.add(
        BudgetTransaction(
            class_id=pr.class_id,
            reference_id=pr.id,
            reference_type="PR",
            transaction_type="consume",
            amount=float(pr.budget_amount),
            created_at=datetime.utcnow(),
        )
    )


def record_pr_budget_return(session: Session, pr: PurchaseRequest) -> None:
    if not has_pr_budget_consume(session, pr.id) or has_pr_budget_return(session, pr.id):
        return
    session.add(
        BudgetTransaction(
            class_id=pr.class_id,
            reference_id=pr.id,
            reference_type="PR",
            transaction_type="return",
            amount=float(pr.budget_amount),
            created_at=datetime.utcnow(),
        )
    )


def log_pr_status_change(
    session: Session, pr_id: int, from_status: Optional[str], to_status: str, user_id: int
) -> None:
    from models import PRStatusHistory

    session.add(
        PRStatusHistory(
            pr_id=pr_id,
            from_status=from_status,
            to_status=to_status,
            changed_by_id=user_id,
            created_at=datetime.utcnow(),
        )
    )


def net_team_pr_budget_allocated(
    session: Session, team_id: int, exclude_pr_id: Optional[int] = None
) -> float:
    q = session.query(PurchaseRequest).filter(
        PurchaseRequest.team_id == team_id,
        PurchaseRequest.status != "rejected",
    )
    if exclude_pr_id is not None:
        q = q.filter(PurchaseRequest.id != exclude_pr_id)
    return sum(float(p.budget_amount) for p in q.all())


def team_budget_cap_remaining(
    session: Session, team_id: int, exclude_pr_id: Optional[int] = None
) -> Tuple[float, float, float]:
    team = session.get(Team, team_id)
    if not team:
        return 0.0, 0.0, 0.0
    cap = float(team.team_budget_amount)
    used = net_team_pr_budget_allocated(session, team_id, exclude_pr_id=exclude_pr_id)
    return cap, used, max(0.0, cap - used)


def _rules_for_table(session: Session, table_name: str) -> List[FieldRule]:
    return session.query(FieldRule).filter_by(table_name=table_name).all()


def validate_form(
    session: Session,
    table_name: str,
    field_values: Dict[str, Any],
    line_items: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, List[str]]:
    messages: List[str] = []
    rules = _rules_for_table(session, table_name)
    for r in rules:
        if r.field_name not in field_values:
            continue
        val = field_values[r.field_name]
        ok = True
        if r.rule_type == "required":
            ok = val is not None and str(val).strip() != ""
        elif r.rule_type == "numeric":
            try:
                float(val)
            except (TypeError, ValueError):
                ok = False
        elif r.rule_type == "min_value":
            try:
                ok = float(val) >= float(r.rule_value)
            except (TypeError, ValueError):
                ok = False
        if not ok:
            messages.append(r.error_message)
    return (len(messages) == 0, messages)


def validate_line_items(session: Session, lines: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    messages: List[str] = []
    rules = _rules_for_table(session, "purchase_request_items")
    sup_ids = {s.id for s in session.query(Supplier).filter_by(is_active=True).all()}
    for row in lines:
        fd = {
            "description": row.get("description"),
            "qty": row.get("qty"),
            "unit_price": row.get("unit_price"),
            "supplier_id": row.get("supplier_id"),
        }
        _, hm = validate_form(session, "purchase_request_items", fd)
        messages.extend(hm)
        sid = row.get("supplier_id")
        if sid is not None and int(sid) not in sup_ids:
            messages.append("Invalid supplier")
    return (len(messages) == 0, messages)


def validate_email_format(email: str) -> bool:
    e = (email or "").strip()
    return "@" in e and "." in e.split("@")[-1] and len(e) >= 5


def list_row_matches_filter(
    search: str,
    status_choice: str,
    row_status: str,
    *text_parts: object,
) -> bool:
    """List/search UI: optional status dropdown ('All' = no filter) and case-insensitive substring search across text_parts."""
    if status_choice != "All" and row_status != status_choice:
        return False
    q = str(search or "").strip().lower()
    if not q:
        return True
    blob = " ".join(str(x).lower() for x in text_parts)
    return q in blob


def ir_attachment_safe_filename(name: str) -> str:
    n = (name or "file").strip().replace("\\", "_").replace("/", "_")
    n = re.sub(r"[^\w.\- ]", "_", n, flags=re.UNICODE).strip()[:200]
    return n or "file"


def save_ir_attachment_file(data_dir: Path, ir_id: int, original_filename: str, body: bytes) -> str:
    """Write bytes under data_dir/ir_attachments/{ir_id}/; return path relative to data_dir (posix)."""
    rel_dir = Path("ir_attachments") / str(ir_id)
    dest_dir = data_dir / rel_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = ir_attachment_safe_filename(original_filename)
    fn = f"{uuid.uuid4().hex[:12]}_{stem}"
    (dest_dir / fn).write_bytes(body)
    return (rel_dir / fn).as_posix()
