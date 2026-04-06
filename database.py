"""SQLite engine, session factory, and lightweight schema migrations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "pms.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_session() -> Session:
    return SessionLocal()


def clear_all_procurement_documents(session: Session) -> None:
    """
    Delete all purchase requests, POs, inventory receipts, return notes, and dependent rows
    (PR messages, PR budget transactions, PR status history, line items, IR attachments).
    Removes files under data/ir_attachments/. Resets document counters for PR, PO, IR, RN.
    Does not delete users, classes, teams, suppliers, or reference/config tables.
    """
    import shutil

    from models import (
        BudgetTransaction,
        DocumentNumbering,
        IRAttachment,
        InventoryReceive,
        Message,
        PRStatusHistory,
        PurchaseOrder,
        PurchaseRequest,
        PurchaseRequestItem,
        ReturnNote,
    )

    ir_att_dir = DATA_DIR / "ir_attachments"
    if ir_att_dir.is_dir():
        shutil.rmtree(ir_att_dir, ignore_errors=True)

    session.query(ReturnNote).delete(synchronize_session=False)
    session.query(IRAttachment).delete(synchronize_session=False)
    session.query(InventoryReceive).delete(synchronize_session=False)
    session.query(PurchaseOrder).delete(synchronize_session=False)
    session.query(Message).filter(Message.reference_type == "PR").delete(synchronize_session=False)
    session.query(BudgetTransaction).filter(BudgetTransaction.reference_type == "PR").delete(
        synchronize_session=False
    )
    session.query(PRStatusHistory).delete(synchronize_session=False)
    session.query(PurchaseRequestItem).delete(synchronize_session=False)
    session.query(PurchaseRequest).delete(synchronize_session=False)

    now_y = datetime.utcnow().year
    for dt in ("PR", "PO", "IR", "RN"):
        row = session.query(DocumentNumbering).filter_by(document_type=dt).first()
        if row:
            row.last_number = 0
            row.year = now_y

    session.commit()


def migrate_sqlite_schema() -> None:
    try:
        insp = inspect(engine)
        tables = insp.get_table_names()
        if "users" not in tables:
            return
        with engine.begin() as conn:

            def user_cols() -> set[str]:
                return {str(r[1]) for r in conn.execute(text("PRAGMA table_info(users)")).fetchall()}

            uc = user_cols()
            if "is_active" not in uc:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"))

            if "inventory_receive" in tables:
                def ir_cols() -> set[str]:
                    return {str(r[1]) for r in conn.execute(text("PRAGMA table_info(inventory_receive)")).fetchall()}

                ic = ir_cols()
                if "received_by_id" not in ic:
                    conn.execute(text("ALTER TABLE inventory_receive ADD COLUMN received_by_id INTEGER"))
                if "updated_at" not in ic:
                    conn.execute(text("ALTER TABLE inventory_receive ADD COLUMN updated_at DATETIME"))
                if "po_document_ok" not in ic:
                    conn.execute(text("ALTER TABLE inventory_receive ADD COLUMN po_document_ok INTEGER DEFAULT 0"))
                if "delivery_note_ok" not in ic:
                    conn.execute(text("ALTER TABLE inventory_receive ADD COLUMN delivery_note_ok INTEGER DEFAULT 0"))
                if "invoice_ok" not in ic:
                    conn.execute(text("ALTER TABLE inventory_receive ADD COLUMN invoice_ok INTEGER DEFAULT 0"))
                if "needs_supplier_resolution" not in ic:
                    conn.execute(
                        text(
                            "ALTER TABLE inventory_receive ADD COLUMN needs_supplier_resolution INTEGER NOT NULL DEFAULT 0"
                        )
                    )
                if "pickup_ready" not in ic:
                    conn.execute(
                        text("ALTER TABLE inventory_receive ADD COLUMN pickup_ready INTEGER NOT NULL DEFAULT 0")
                    )
                if "requester_accepted_at" not in ic:
                    conn.execute(text("ALTER TABLE inventory_receive ADD COLUMN requester_accepted_at DATETIME"))
                if "requester_accepted_by_id" not in ic:
                    conn.execute(text("ALTER TABLE inventory_receive ADD COLUMN requester_accepted_by_id INTEGER"))
                if "requester_accepted_at" in ir_cols():
                    conn.execute(
                        text(
                            "UPDATE inventory_receive SET status = 'closed' "
                            "WHERE requester_accepted_at IS NOT NULL "
                            "AND (status IS NULL OR LOWER(TRIM(CAST(status AS TEXT))) IN ('open', 'ready_for_pickup'))"
                        )
                    )

            if "return_notes" in tables:
                def rn_cols() -> set[str]:
                    return {str(r[1]) for r in conn.execute(text("PRAGMA table_info(return_notes)")).fetchall()}

                rc = rn_cols()
                if "product_dropped_off" not in rc:
                    conn.execute(
                        text("ALTER TABLE return_notes ADD COLUMN product_dropped_off INTEGER NOT NULL DEFAULT 0")
                    )
                if "updated_at" not in rc:
                    conn.execute(text("ALTER TABLE return_notes ADD COLUMN updated_at DATETIME"))

            if "teams" in tables:
                def team_cols() -> set[str]:
                    return {str(r[1]) for r in conn.execute(text("PRAGMA table_info(teams)")).fetchall()}

                if "team_budget_amount" not in team_cols():
                    conn.execute(
                        text("ALTER TABLE teams ADD COLUMN team_budget_amount REAL NOT NULL DEFAULT 0")
                    )

            if "purchase_orders" in tables:
                def po_cols() -> set[str]:
                    return {str(r[1]) for r in conn.execute(text("PRAGMA table_info(purchase_orders)")).fetchall()}

                if "pr_line_item_id" not in po_cols():
                    conn.execute(
                        text(
                            "ALTER TABLE purchase_orders ADD COLUMN pr_line_item_id INTEGER "
                            "REFERENCES purchase_request_items (id)"
                        )
                    )

            if "team_members" not in tables:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS team_members (
                            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            team_id INTEGER NOT NULL,
                            created_at DATETIME,
                            FOREIGN KEY(user_id) REFERENCES users (id),
                            FOREIGN KEY(team_id) REFERENCES teams (id),
                            UNIQUE (user_id, team_id)
                        )
                        """
                    )
                )

            if "purchase_request_items" in tables:
                def pri_cols() -> set[str]:
                    return {str(r[1]) for r in conn.execute(text("PRAGMA table_info(purchase_request_items)")).fetchall()}

                pc = pri_cols()
                added = False
                if "approver_decision" not in pc:
                    conn.execute(text("ALTER TABLE purchase_request_items ADD COLUMN approver_decision VARCHAR(20)"))
                    added = True
                if "hop_approved" not in pc:
                    conn.execute(
                        text("ALTER TABLE purchase_request_items ADD COLUMN hop_approved INTEGER NOT NULL DEFAULT 0")
                    )
                    added = True
                if added:
                    conn.execute(
                        text(
                            """
                            UPDATE purchase_request_items SET approver_decision = 'approved', hop_approved = 1
                            WHERE pr_id IN (SELECT id FROM purchase_requests WHERE status = 'approved')
                            """
                        )
                    )
                    conn.execute(
                        text(
                            """
                            UPDATE purchase_request_items SET approver_decision = 'approved', hop_approved = 0
                            WHERE pr_id IN (SELECT id FROM purchase_requests WHERE status IN ('reviewed','approved_by_approver'))
                            """
                        )
                    )
    except Exception:
        pass


def ensure_budget_management_menu(session: Session) -> None:
    """Add menu_visibility for budget_management for existing DBs (master + HoP only)."""
    from models import MenuVisibility, Role

    if session.query(MenuVisibility).filter_by(menu_key="budget_management").first():
        return
    for role in session.query(Role).all():
        can_view = bool(role.is_master or role.role_name == "head_of_purchasing")
        session.add(
            MenuVisibility(
                role_id=role.id,
                menu_key="budget_management",
                can_view=can_view,
                show_own_only=False,
                created_at=datetime.utcnow(),
            )
        )
    session.commit()


def ensure_ir_closed_document_status(session: Session) -> None:
    """Add IR status 'closed' (label Closed) for DBs seeded before that status existed."""
    from models import DocumentStatus

    exists = (
        session.query(DocumentStatus)
        .filter_by(document_type="IR", status_code="closed")
        .first()
    )
    if exists:
        return
    session.add(
        DocumentStatus(
            document_type="IR",
            status_code="closed",
            status_label="Closed",
            status_color="green",
            order_sequence=3,
            is_final=True,
            description=None,
        )
    )
    session.commit()


def ensure_ir_ready_for_pickup_document_status(session: Session) -> None:
    """Add IR status ready_for_pickup for DBs that predate the pickup workflow."""
    from models import DocumentStatus

    if session.query(DocumentStatus).filter_by(document_type="IR", status_code="ready_for_pickup").first():
        return
    session.add(
        DocumentStatus(
            document_type="IR",
            status_code="ready_for_pickup",
            status_label="Ready to pick up",
            status_color="yellow",
            order_sequence=2,
            is_final=False,
            description=None,
        )
    )
    session.commit()


def ensure_rn_workflow_permissions(session: Session) -> None:
    """Ensure return-note workflow rows exist (older DBs may lack RN status_action_permissions)."""
    from models import Role, StatusActionPermission

    def _role(name: str):
        return session.query(Role).filter_by(role_name=name).first()

    specs = [
        ("RN", "draft", "requester", "submit", True, "Submit for HoP approval", "submitted"),
        ("RN", "draft", "master", "submit", True, "Submit for HoP approval", "submitted"),
        ("RN", "draft", "requester", "cancel", True, "Cancel", "cancelled"),
        ("RN", "draft", "master", "cancel", True, "Cancel", "cancelled"),
        ("RN", "submitted", "head_of_purchasing", "approve", True, "Approve", "approved"),
        ("RN", "submitted", "master", "approve", True, "Approve", "approved"),
        ("RN", "submitted", "head_of_purchasing", "reject", True, "Reject", "rejected"),
        ("RN", "submitted", "master", "reject", True, "Reject", "rejected"),
        ("RN", "approved", "requester", "complete", True, "Completed", "closed"),
        ("RN", "approved", "master", "complete", True, "Completed", "closed"),
        ("RN", "approved", "head_of_purchasing", "complete", True, "Completed", "closed"),
        ("RN", "approved", "purchasing_team", "complete", True, "Completed", "closed"),
        ("RN", "approved", "requester", "void", True, "Cancel", "rejected"),
        ("RN", "approved", "master", "void", True, "Cancel", "rejected"),
        ("RN", "approved", "head_of_purchasing", "void", True, "Cancel", "rejected"),
        ("RN", "approved", "purchasing_team", "void", True, "Cancel", "rejected"),
    ]
    added = False
    for dt, sc, rname, ak, allowed, label, nxt in specs:
        role = _role(rname)
        if not role:
            continue
        exists = (
            session.query(StatusActionPermission)
            .filter_by(
                document_type=dt,
                status_code=sc,
                role_id=role.id,
                action_key=ak,
            )
            .first()
        )
        if exists:
            continue
        session.add(
            StatusActionPermission(
                document_type=dt,
                status_code=sc,
                role_id=role.id,
                action_key=ak,
                is_allowed=allowed,
                button_label=label,
                next_status=nxt,
            )
        )
        added = True
    if added:
        session.commit()


def ensure_rn_cancelled_document_status(session: Session) -> None:
    """Add RN status 'cancelled' for DBs seeded before that status existed."""
    from models import DocumentStatus

    if session.query(DocumentStatus).filter_by(document_type="RN", status_code="cancelled").first():
        return
    session.add(
        DocumentStatus(
            document_type="RN",
            status_code="cancelled",
            status_label="Cancelled",
            status_color="gray",
            order_sequence=6,
            is_final=True,
            description=None,
        )
    )
    session.commit()


def ensure_pr_reviewed_hop_actions(session: Session) -> None:
    """Ensure Head of Purchasing can reject PRs in reviewed status (older DBs may lack this row)."""
    from models import Role, StatusActionPermission

    hop = session.query(Role).filter_by(role_name="head_of_purchasing").first()
    if not hop:
        return
    exists = (
        session.query(StatusActionPermission)
        .filter_by(
            document_type="PR",
            status_code="reviewed",
            role_id=hop.id,
            action_key="reject",
        )
        .first()
    )
    if exists:
        return
    session.add(
        StatusActionPermission(
            document_type="PR",
            status_code="reviewed",
            role_id=hop.id,
            action_key="reject",
            is_allowed=True,
            button_label="Reject PR",
            next_status="rejected",
        )
    )
    session.commit()
