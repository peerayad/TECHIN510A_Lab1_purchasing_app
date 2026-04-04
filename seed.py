"""One-time database seed: roles, master data, permissions, sample transactions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from auth import hash_password
from models import (
    AppUser,
    BudgetTransaction,
    Class,
    DocumentNumbering,
    DocumentStatus,
    FieldLockConfig,
    FieldRule,
    InventoryReceive,
    MenuVisibility,
    Permission,
    PurchaseOrder,
    PurchaseRequest,
    PurchaseRequestItem,
    PurchasingRound,
    Role,
    StatusActionPermission,
    StudentList,
    Supplier,
    Team,
    TeamMembership,
)


def _role_id(session: Session, name: str) -> int:
    return session.query(Role).filter_by(role_name=name).one().id


def seed_if_empty(session: Session) -> bool:
    if session.query(Role).first() is not None:
        return False
    try:
        _seed_data(session)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise


def _seed_data(session: Session) -> None:
    roles_data = [
        ("master", "Full system access", True),
        ("requester", "Creates and submits purchase requests", False),
        ("approver", "Line-level approval for PRs", False),
        ("head_of_purchasing", "Final line approval for PRs", False),
        ("purchasing_team", "Creates POs and handles inventory", False),
    ]
    for name, desc, is_m in roles_data:
        session.add(Role(role_name=name, description=desc, is_master=is_m))
    session.flush()

    pr_fields = [
        "pr_number",
        "class_id",
        "team_id",
        "purchasing_round_id",
        "budget_amount",
        "status",
        "requester_id",
        "created_at",
    ]

    def add_perms(role_name: str, edit_fields: set, view_all: bool = True):
        rid = _role_id(session, role_name)
        for f in pr_fields:
            session.add(
                Permission(
                    role_id=rid,
                    table_name="purchase_requests",
                    field_name=f,
                    can_view=view_all,
                    can_edit=f in edit_fields,
                )
            )

    add_perms("master", set(pr_fields))
    add_perms("requester", {"class_id", "team_id", "purchasing_round_id"})
    add_perms("approver", {"status"})
    add_perms("head_of_purchasing", {"status"})
    add_perms("purchasing_team", {"status"})

    students = [
        ("Master", "Admin", "master@school.com", "STU001"),
        ("Jane", "Smith", "requester@school.com", "STU002"),
        ("Bob", "Jones", "approver@school.com", "STU003"),
        ("Alice", "Brown", "head@school.com", "STU004"),
        ("Carol", "White", "purchasing@school.com", "STU005"),
    ]
    for fn, ln, em, sid in students:
        session.add(
            StudentList(
                first_name=fn,
                last_name=ln,
                email=em,
                student_id=sid,
                is_active=True,
                created_at=datetime.utcnow(),
            )
        )
    session.flush()

    def sl_id(email: str) -> int:
        return session.query(StudentList).filter_by(email=email).one().id

    pw_m = hash_password("master123")
    pw_t = hash_password("test123")
    for email, sl_id_, pw, rname in [
        ("master@school.com", sl_id("master@school.com"), pw_m, "master"),
        ("requester@school.com", sl_id("requester@school.com"), pw_t, "requester"),
        ("approver@school.com", sl_id("approver@school.com"), pw_t, "approver"),
        ("head@school.com", sl_id("head@school.com"), pw_t, "head_of_purchasing"),
        ("purchasing@school.com", sl_id("purchasing@school.com"), pw_t, "purchasing_team"),
    ]:
        session.add(
            AppUser(
                student_list_id=sl_id_,
                email=email,
                password=pw,
                role_id=_role_id(session, rname),
                is_active=True,
                created_at=datetime.utcnow(),
            )
        )

    for code, name, cn, ph, em, addr in [
        ("SUP001", "Amazon", "Support", "800-000-0001", "amazon@example.com", "USA"),
        ("SUP002", "Digikey", "Sales", "800-000-0002", "digikey@example.com", "USA"),
        ("SUP003", "Mouser", "Sales", "800-000-0003", "mouser@example.com", "USA"),
    ]:
        session.add(
            Supplier(
                supplier_code=code,
                supplier_name=name,
                contact_name=cn,
                phone=ph,
                email=em,
                address=addr,
                is_active=True,
            )
        )

    for code, cname, year, budget, desc in [
        ("CS101", "Introduction to Computer Science", "2025-2026", 5000.0, "Undergrad CS"),
        ("EE201", "Circuits and Systems", "2025-2026", 8000.0, "EE lab"),
    ]:
        session.add(
            Class(
                class_code=code,
                class_name=cname,
                academic_year=year,
                budget_amount=budget,
                description=desc,
            )
        )
    session.flush()

    for c in session.query(Class).order_by(Class.id).all():
        for i, suffix in enumerate(["Alpha", "Beta", "Gamma"], start=1):
            session.add(
                Team(
                    team_code=f"{c.class_code}-T{i}",
                    team_name=f"Team {suffix}",
                    class_id=c.id,
                    team_budget_amount=2000.0,
                    is_active=True,
                )
            )
        for rn in ("Round 1", "Round 2"):
            session.add(
                PurchasingRound(
                    round_name=rn,
                    class_id=c.id,
                    academic_year=c.academic_year,
                    is_active=True,
                )
            )
    session.flush()

    ru = session.query(AppUser).filter_by(email="requester@school.com").one()
    cs = session.query(Class).filter_by(class_code="CS101").one()
    t1 = session.query(Team).filter_by(class_id=cs.id, team_code="CS101-T1").one()
    session.add(TeamMembership(user_id=ru.id, team_id=t1.id, created_at=datetime.utcnow()))

    menu_keys = [
        "purchase_request",
        "purchase_order",
        "inventory_receipt",
        "inventory_return",
        "user_management",
        "budget_management",
    ]
    defaults = {
        "master": (True, False),
        "requester": (True, True),
        "approver": (True, False),
        "head_of_purchasing": (True, False),
        "purchasing_team": (True, False),
    }
    for rname, (cv, so) in defaults.items():
        rid = _role_id(session, rname)
        for mk in menu_keys:
            if mk == "user_management":
                can_v = rname == "master"
            elif mk == "budget_management":
                can_v = rname in ("master", "head_of_purchasing")
            else:
                can_v = cv
            session.add(
                MenuVisibility(
                    role_id=rid,
                    menu_key=mk,
                    can_view=can_v,
                    show_own_only=so if mk == "purchase_request" else False,
                    created_at=datetime.utcnow(),
                )
            )

    pr_item_rules = [
        ("purchase_requests", "class_id", "required", "true", "Please select a class"),
        ("purchase_requests", "team_id", "required", "true", "Please select a team"),
        ("purchase_requests", "purchasing_round_id", "required", "true", "Please select a purchasing round"),
        ("purchase_request_items", "description", "required", "true", "Description is required"),
        ("purchase_request_items", "qty", "required", "true", "Qty must be greater than 0"),
        ("purchase_request_items", "qty", "numeric", "true", "Qty must be a number"),
        ("purchase_request_items", "qty", "min_value", "1", "Qty must be at least 1"),
        ("purchase_request_items", "unit_price", "required", "true", "Unit price required"),
        ("purchase_request_items", "unit_price", "numeric", "true", "Unit price must be a number"),
        ("purchase_request_items", "unit_price", "min_value", "0.01", "Unit price must be greater than 0"),
        ("purchase_request_items", "supplier_id", "required", "true", "Please select a supplier"),
    ]
    for tn, fn, rt, rv, em in pr_item_rules:
        session.add(FieldRule(table_name=tn, field_name=fn, rule_type=rt, rule_value=rv, error_message=em))

    for dt, sc, sl, col, seq, fin, desc in [
        ("PR", "draft", "Draft", "gray", 1, False, None),
        ("PR", "submitted", "Submitted", "blue", 2, False, None),
        ("PR", "reviewed", "Reviewed", "yellow", 3, False, None),
        ("PR", "approved", "Approved", "green", 4, False, None),
        ("PR", "rejected", "Rejected", "red", 5, True, None),
        ("PO", "open", "Open", "blue", 1, False, None),
        ("PO", "success", "Success", "green", 2, True, None),
        ("PO", "rejected", "Rejected", "red", 3, True, None),
        ("IR", "open", "Open", "blue", 1, False, None),
        ("IR", "accepted", "Accepted", "green", 2, True, None),
        ("IR", "returning", "Returning", "red", 3, True, None),
        ("RN", "draft", "Draft", "gray", 1, False, None),
        ("RN", "submitted", "Submitted", "blue", 2, False, None),
        ("RN", "approved", "Approved", "yellow", 3, False, None),
        ("RN", "closed", "Closed", "green", 4, True, None),
        ("RN", "rejected", "Rejected", "red", 5, True, None),
    ]:
        session.add(
            DocumentStatus(
                document_type=dt,
                status_code=sc,
                status_label=sl,
                status_color=col,
                order_sequence=seq,
                is_final=fin,
                description=desc,
            )
        )

    sap_rows = [
        ("PR", "draft", "requester", "edit", True, "Edit", "draft"),
        ("PR", "draft", "requester", "submit", True, "Submit", "submitted"),
        ("PR", "draft", "requester", "delete", True, "Delete", None),
        ("PR", "draft", "master", "edit", True, "Edit", "draft"),
        ("PR", "draft", "master", "submit", True, "Submit", "submitted"),
        ("PR", "draft", "master", "delete", True, "Delete", None),
        ("PR", "submitted", "approver", "reject", True, "Reject PR", "rejected"),
        ("PR", "submitted", "master", "reject", True, "Reject PR", "rejected"),
        ("PR", "reviewed", "head_of_purchasing", "reject", True, "Reject PR", "rejected"),
        ("PR", "reviewed", "master", "reject", True, "Reject PR", "rejected"),
        ("PR", "approved", "purchasing_team", "create_po", True, "Create PO", None),
        ("PR", "approved", "master", "create_po", True, "Create PO", None),
        ("IR", "open", "purchasing_team", "verify", True, "Verify", "open"),
        ("IR", "open", "master", "verify", True, "Verify", "open"),
        ("RN", "draft", "requester", "submit", True, "Submit", "submitted"),
        ("RN", "draft", "master", "submit", True, "Submit", "submitted"),
        ("RN", "submitted", "head_of_purchasing", "approve", True, "Approve", "approved"),
        ("RN", "submitted", "master", "approve", True, "Approve", "approved"),
    ]
    for dt, sc, rname, ak, allowed, label, nxt in sap_rows:
        session.add(
            StatusActionPermission(
                document_type=dt,
                status_code=sc,
                role_id=_role_id(session, rname),
                action_key=ak,
                is_allowed=allowed,
                button_label=label,
                next_status=nxt,
            )
        )

    for dt, sc, tn, fn, locked in [
        ("PR", "submitted", "purchase_requests", "class_id", True),
        ("PR", "reviewed", "purchase_requests", "class_id", True),
        ("PR", "approved", "purchase_requests", "class_id", True),
    ]:
        session.add(
            FieldLockConfig(
                document_type=dt,
                status_code=sc,
                table_name=tn,
                field_name=fn,
                locked=locked,
            )
        )

    for dt, prefix, year, lastn, pad in [
        ("PR", "PR", 2026, 0, 5),
        ("PO", "PO", 2026, 0, 5),
        ("IR", "IR", 2026, 0, 5),
        ("RN", "RN", 2026, 0, 5),
    ]:
        session.add(
            DocumentNumbering(
                document_type=dt,
                prefix=prefix,
                year=year,
                last_number=lastn,
                pad_length=pad,
            )
        )
    session.flush()

    req_user = session.query(AppUser).filter_by(email="requester@school.com").one()
    c1 = session.query(Class).filter_by(class_code="CS101").one()
    team1 = session.query(Team).filter_by(team_code="CS101-T1").one()
    r1 = session.query(PurchasingRound).filter_by(class_id=c1.id, round_name="Round 1").one()
    sup1 = session.query(Supplier).filter_by(supplier_code="SUP001").one()
    sup2 = session.query(Supplier).filter_by(supplier_code="SUP002").one()

    def add_pr(num: str, status: str, lines: list):
        pr = PurchaseRequest(
            pr_number=num,
            requester_id=req_user.id,
            class_id=c1.id,
            team_id=team1.id,
            purchasing_round_id=r1.id,
            budget_amount=0.0,
            status=status,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(pr)
        session.flush()
        tot = 0.0
        for i, (desc, qty, price, sid) in enumerate(lines, start=1):
            st = qty * price
            tot += st
            ad = None
            ha = False
            if status == "approved":
                ad, ha = "approved", True
            elif status == "reviewed":
                ad, ha = "approved", False
            elif status == "submitted":
                ad, ha = None, False
            session.add(
                PurchaseRequestItem(
                    pr_id=pr.id,
                    item_no=i,
                    description=desc,
                    qty=qty,
                    unit_price=price,
                    sub_total=st,
                    supplier_id=sid,
                    link=None,
                    created_at=datetime.utcnow(),
                    approver_decision=ad,
                    hop_approved=ha,
                )
            )
        pr.budget_amount = tot

    add_pr(
        "PR2026-00001",
        "draft",
        [("Arduino starter kit", 2, 45.0, sup1.id), ("Jumper wires", 5, 3.5, sup2.id)],
    )
    add_pr("PR2026-00002", "submitted", [("Soldering iron", 1, 89.99, sup1.id)])
    add_pr(
        "PR2026-00003",
        "approved",
        [("Breadboard", 3, 12.0, sup2.id), ("Resistor kit", 1, 25.0, sup1.id)],
    )

    for pr in session.query(PurchaseRequest).filter(PurchaseRequest.status.in_(("submitted", "reviewed", "approved"))).all():
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

    dn = session.query(DocumentNumbering).filter_by(document_type="PR").one()
    dn.last_number = 3
    dn.year = 2026

    pu = session.query(AppUser).filter_by(email="purchasing@school.com").one()
    appr = session.query(PurchaseRequest).filter_by(pr_number="PR2026-00003").one()
    session.add(
        PurchaseOrder(
            po_number="PO2026-00001",
            pr_id=appr.id,
            purchasing_team_id=pu.id,
            status="open",
            created_at=datetime.utcnow(),
        )
    )
    session.flush()
    po = session.query(PurchaseOrder).filter_by(po_number="PO2026-00001").one()
    session.add(
        InventoryReceive(
            ir_number="IR2026-00001",
            po_id=po.id,
            received_by_id=pu.id,
            status="open",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    dn_po = session.query(DocumentNumbering).filter_by(document_type="PO").one()
    dn_po.last_number = max(dn_po.last_number, 1)
    dn_ir = session.query(DocumentNumbering).filter_by(document_type="IR").one()
    dn_ir.last_number = max(dn_ir.last_number, 1)
