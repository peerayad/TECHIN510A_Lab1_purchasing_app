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
