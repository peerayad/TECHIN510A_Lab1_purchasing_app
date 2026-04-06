"""Master-only user accounts and master data (students, teams, suppliers, etc.)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Set

import pandas as pd
import streamlit as st
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from auth import hash_password
from models import (
    AppUser,
    Class,
    Permission,
    PurchasingRound,
    Role,
    StudentList,
    Supplier,
    Team,
    TeamMembership,
)
from database import clear_all_procurement_documents
from utils import validate_email_format as vef

PR_TABLE = "purchase_requests"
PR_FIELDS = [
    "pr_number",
    "class_id",
    "team_id",
    "purchasing_round_id",
    "budget_amount",
    "status",
    "requester_id",
    "created_at",
]


def render_user_management(session: Session) -> None:
    st.title("User management")
    t1, t2, t3, t4, t5 = st.tabs(
        ["Student list", "User accounts", "Roles & permissions", "Master data", "Data maintenance"]
    )
    with t1:
        _tab_students(session)
    with t2:
        _tab_users(session)
    with t3:
        _tab_permissions(session)
    with t4:
        _tab_master_data(session)
    with t5:
        _tab_data_maintenance(session)


def _tab_data_maintenance(session: Session) -> None:
    st.subheader("Clear procurement documents")
    st.warning(
        "This permanently deletes **all** purchase requests, purchase orders, inventory receipts, "
        "return notes, PR line items, PR status history, PR messages, and PR budget transactions. "
        "Uploaded IR files under **data/ir_attachments/** are removed. "
        "Document numbers for PR, PO, IR, and RN reset so the next documents start from 1 again. "
        "Users, classes, teams, suppliers, and settings are **not** removed."
    )
    if st.checkbox("I understand this cannot be undone.", key="um_clear_proc_confirm"):
        if st.button("Delete all PR / PO / IR / RN", type="primary", key="um_clear_proc_run"):
            clear_all_procurement_documents(session)
            st.success("All procurement documents were cleared. You can create new requests.")
            st.rerun()


def _tab_students(session: Session) -> None:
    st.subheader("Students")
    rows = session.query(StudentList).order_by(StudentList.last_name, StudentList.first_name).all()
    if rows:
        df = pd.DataFrame(
            [
                {
                    "id": s.id,
                    "first_name": s.first_name,
                    "last_name": s.last_name,
                    "email": s.email,
                    "student_id": s.student_id,
                    "is_active": s.is_active,
                }
                for s in rows
            ]
        )
        ed = st.data_editor(df, disabled=["id", "email", "student_id"], hide_index=True, use_container_width=True)
        if st.button("Save student changes"):
            for _, row in ed.iterrows():
                s = session.get(StudentList, int(row["id"]))
                if s:
                    s.first_name = str(row["first_name"]).strip()
                    s.last_name = str(row["last_name"]).strip()
                    s.is_active = bool(row["is_active"])
            session.commit()
            st.success("Saved.")
            st.rerun()
    st.divider()
    st.markdown("#### Add student")
    with st.form("add_student"):
        fn = st.text_input("First name")
        ln = st.text_input("Last name")
        em = st.text_input("Email")
        sid = st.text_input("Student ID")
        if st.form_submit_button("Add student"):
            fn, ln, em, sid = fn.strip(), ln.strip(), em.strip(), sid.strip()
            if not all([fn, ln, em, sid]):
                st.error("All fields required.")
            elif not vef(em):
                st.error("Invalid email.")
            elif session.query(StudentList).filter(func.lower(StudentList.email) == em.lower()).first():
                st.error("Email exists.")
            elif session.query(StudentList).filter_by(student_id=sid).first():
                st.error("Student ID in use.")
            else:
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
                session.commit()
                st.success("Added.")
                st.rerun()


def _tab_users(session: Session) -> None:
    st.subheader("User accounts")
    users = session.query(AppUser).options(joinedload(AppUser.student), joinedload(AppUser.role)).all()
    roles = session.query(Role).order_by(Role.role_name).all()
    role_map = {r.role_name: r.id for r in roles}
    for u in users:
        st.markdown(f"**{u.email}** — {u.student.first_name} {u.student.last_name} ({u.role.role_name})")
        c1, c2 = st.columns(2)
        with c1:
            new_r = st.selectbox(
                "Role",
                list(role_map.keys()),
                index=list(role_map.keys()).index(u.role.role_name),
                key=f"ur_{u.id}",
            )
        with c2:
            active = st.checkbox("Active", value=u.is_active, key=f"ua_{u.id}")
        if st.button("Save user", key=f"us_{u.id}"):
            u.role_id = role_map[new_r]
            u.is_active = active
            session.commit()
            st.rerun()
    st.divider()
    st.markdown("#### New user (existing student)")
    studs = session.query(StudentList).outerjoin(AppUser).filter(AppUser.id.is_(None)).all()
    if not studs:
        st.info("All students have accounts, or add students first.")
        return
    sl_map = {f"{s.email} — {s.first_name} {s.last_name}": s.id for s in studs}
    pick = st.selectbox("Student", list(sl_map.keys()))
    new_em = st.text_input("Login email (often same as student email)")
    pw = st.text_input("Password", type="password")
    rname = st.selectbox("Role", list(role_map.keys()), key="new_ur")
    if st.button("Create user"):
        em = new_em.strip() or session.get(StudentList, sl_map[pick]).email
        if not pw or len(pw) < 4:
            st.error("Password required (min 4 chars).")
        elif session.query(AppUser).filter(func.lower(AppUser.email) == em.lower()).first():
            st.error("Email already used.")
        else:
            session.add(
                AppUser(
                    student_list_id=sl_map[pick],
                    email=em,
                    password=hash_password(pw),
                    role_id=role_map[rname],
                    is_active=True,
                    created_at=datetime.utcnow(),
                )
            )
            session.commit()
            st.success("User created.")
            st.rerun()


def _tab_permissions(session: Session) -> None:
    st.subheader("PR field permissions by role")
    roles = [r for r in session.query(Role).order_by(Role.role_name).all() if not r.is_master]
    if not roles:
        return
    sel = st.selectbox("Role", roles, format_func=lambda r: r.role_name)
    perms = session.query(Permission).filter_by(role_id=sel.id, table_name=PR_TABLE).all()
    pmap = {p.field_name: p for p in perms}
    rows = []
    for f in PR_FIELDS:
        p = pmap.get(f)
        rows.append({"field_name": f, "can_view": p.can_view if p else False, "can_edit": p.can_edit if p else False})
    ed = st.data_editor(
        pd.DataFrame(rows),
        column_config={
            "field_name": st.column_config.TextColumn("Field", disabled=True),
            "can_view": st.column_config.CheckboxColumn("Can view"),
            "can_edit": st.column_config.CheckboxColumn("Can edit"),
        },
        hide_index=True,
        use_container_width=True,
        key=f"perm_{sel.id}",
    )
    if st.button("Save permissions", key=f"savep_{sel.id}"):
        for _, row in ed.iterrows():
            fn = row["field_name"]
            p = session.query(Permission).filter_by(role_id=sel.id, table_name=PR_TABLE, field_name=fn).first()
            if p:
                p.can_view = bool(row["can_view"])
                p.can_edit = bool(row["can_edit"])
            else:
                session.add(
                    Permission(
                        role_id=sel.id,
                        table_name=PR_TABLE,
                        field_name=fn,
                        can_view=bool(row["can_view"]),
                        can_edit=bool(row["can_edit"]),
                    )
                )
        session.commit()
        st.success("Saved.")
        st.rerun()


def _tab_master_data(session: Session) -> None:
    st.subheader("Master data")
    a, b, c, d, e = st.tabs(["Suppliers", "Classes", "Teams", "Team members", "Purchasing rounds"])
    with a:
        _master_suppliers(session)
    with b:
        _master_classes(session)
    with c:
        _master_teams(session)
    with d:
        _master_team_members(session)
    with e:
        _master_rounds(session)


def _master_suppliers(session: Session) -> None:
    sups = session.query(Supplier).order_by(Supplier.supplier_code).all()
    if sups:
        df = pd.DataFrame(
            [
                {
                    "id": s.id,
                    "supplier_code": s.supplier_code,
                    "supplier_name": s.supplier_name,
                    "is_active": s.is_active,
                }
                for s in sups
            ]
        )
        ed = st.data_editor(df, disabled=["id"], hide_index=True, use_container_width=True)
        if st.button("Save suppliers"):
            for _, row in ed.iterrows():
                s = session.get(Supplier, int(row["id"]))
                if s:
                    s.supplier_code = str(row["supplier_code"]).strip()
                    s.supplier_name = str(row["supplier_name"]).strip()
                    s.is_active = bool(row["is_active"])
            session.commit()
            st.rerun()


def _master_classes(session: Session) -> None:
    cls_rows = session.query(Class).order_by(Class.class_code).all()
    if cls_rows:
        df = pd.DataFrame(
            [
                {
                    "id": c.id,
                    "class_code": c.class_code,
                    "class_name": c.class_name,
                    "academic_year": c.academic_year,
                    "budget_amount": float(c.budget_amount),
                }
                for c in cls_rows
            ]
        )
        ed = st.data_editor(df, disabled=["id"], hide_index=True, use_container_width=True)
        if st.button("Save classes"):
            for _, row in ed.iterrows():
                c = session.get(Class, int(row["id"]))
                if c:
                    c.class_code = str(row["class_code"]).strip()
                    c.class_name = str(row["class_name"]).strip()
                    c.academic_year = str(row["academic_year"]).strip()
                    c.budget_amount = float(row["budget_amount"])
            session.commit()
            st.rerun()


def _master_teams(session: Session) -> None:
    classes = session.query(Class).order_by(Class.class_code).all()
    if not classes:
        return
    cmap = {f"{c.class_code} — {c.class_name}": c.id for c in classes}
    clab = st.selectbox("Class", list(cmap.keys()))
    cid = cmap[clab]
    teams = session.query(Team).filter_by(class_id=cid).order_by(Team.team_code).all()
    if teams:
        df = pd.DataFrame(
            [
                {
                    "id": t.id,
                    "team_code": t.team_code,
                    "team_name": t.team_name,
                    "team_budget_amount": float(t.team_budget_amount),
                    "is_active": t.is_active,
                }
                for t in teams
            ]
        )
        ed = st.data_editor(df, disabled=["id"], hide_index=True, use_container_width=True)
        if st.button("Save teams"):
            for _, row in ed.iterrows():
                t = session.get(Team, int(row["id"]))
                if t:
                    t.team_code = str(row["team_code"]).strip()
                    t.team_name = str(row["team_name"]).strip()
                    t.team_budget_amount = float(row["team_budget_amount"])
                    t.is_active = bool(row["is_active"])
            session.commit()
            st.rerun()


def _master_team_members(session: Session) -> None:
    st.caption("Requesters only see classes/teams they belong to when creating PRs.")
    users = (
        session.query(AppUser)
        .options(joinedload(AppUser.student), joinedload(AppUser.role))
        .order_by(AppUser.email)
        .all()
    )
    if not users:
        return
    labels = [f"{u.email} — {u.student.first_name} {u.student.last_name} ({u.role.role_name})" for u in users]
    pick = st.selectbox("User", labels)
    u = users[labels.index(pick)]
    teams = (
        session.query(Team)
        .join(Class, Team.class_id == Class.id)
        .options(joinedload(Team.class_))
        .filter(Team.is_active.is_(True))
        .order_by(Class.class_code, Team.team_code)
        .all()
    )
    team_rows: List[tuple[str, int]] = [
        (f"{t.class_.class_code} — {t.team_code} — {t.team_name}", t.id) for t in teams
    ]
    labels_t = [r[0] for r in team_rows]
    tid_by = dict(team_rows)
    cur: Set[int] = {m.team_id for m in session.query(TeamMembership).filter_by(user_id=u.id).all()}
    default = [lb for lb, tid in team_rows if tid in cur]
    chosen = st.multiselect("Teams", options=labels_t, default=default, key=f"tm_{u.id}")
    if st.button("Save memberships", key=f"tms_{u.id}"):
        session.query(TeamMembership).filter_by(user_id=u.id).delete(synchronize_session=False)
        now = datetime.utcnow()
        for lb in chosen:
            session.add(TeamMembership(user_id=u.id, team_id=tid_by[lb], created_at=now))
        session.commit()
        st.success("Saved.")
        st.rerun()


def _master_rounds(session: Session) -> None:
    classes = session.query(Class).order_by(Class.class_code).all()
    if not classes:
        return
    cmap = {f"{c.class_code} — {c.class_name}": c.id for c in classes}
    clab = st.selectbox("Class (rounds)", list(cmap.keys()))
    cid = cmap[clab]
    rounds = session.query(PurchasingRound).filter_by(class_id=cid).order_by(PurchasingRound.round_name).all()
    if rounds:
        df = pd.DataFrame(
            [
                {"id": r.id, "round_name": r.round_name, "academic_year": r.academic_year, "is_active": r.is_active}
                for r in rounds
            ]
        )
        ed = st.data_editor(df, disabled=["id"], hide_index=True, use_container_width=True)
        if st.button("Save rounds"):
            for _, row in ed.iterrows():
                r = session.get(PurchasingRound, int(row["id"]))
                if r:
                    r.round_name = str(row["round_name"]).strip()
                    r.academic_year = str(row["academic_year"]).strip()
                    r.is_active = bool(row["is_active"])
            session.commit()
            st.rerun()
