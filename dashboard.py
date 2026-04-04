"""Home dashboard and menu visibility helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import streamlit as st
from sqlalchemy.orm import Session

from models import AppUser, MenuVisibility, PurchaseRequest, ReturnNote


@dataclass
class MenuView:
    can_view: bool
    show_own_only: bool


def load_menu_visibility(session: Session, role_id: int) -> Dict[str, MenuView]:
    rows = session.query(MenuVisibility).filter_by(role_id=role_id).all()
    return {
        r.menu_key: MenuView(can_view=bool(r.can_view), show_own_only=bool(r.show_own_only))
        for r in rows
    }


def user_can_manage_budget(user: AppUser) -> bool:
    return user.role.is_master or user.role.role_name == "head_of_purchasing"


def render_dashboard(session: Session, user: AppUser) -> None:
    st.title("Dashboard")
    st.caption(f"Signed in as **{user.email}** ({user.role.role_name.replace('_', ' ')})")

    mv = load_menu_visibility(session, user.role.id)
    by_key = {k: v for k, v in mv.items() if v.can_view}

    if "purchase_request" in by_key:
        q = session.query(PurchaseRequest)
        if by_key["purchase_request"].show_own_only and not user.role.is_master:
            q = q.filter(PurchaseRequest.requester_id == user.id)
        n_pr = q.count()
        st.metric("Purchase requests (visible)", n_pr)

    if "inventory_return" in by_key:
        q = session.query(ReturnNote)
        n_rn = q.filter(ReturnNote.status.in_(("draft", "submitted", "approved"))).count()
        st.metric("Return notes (active pipeline)", n_rn)

    if user.role.is_master:
        st.divider()
        if st.button("Open user management", type="primary", key="dash_um"):
            st.session_state["pms_navigate_to_page"] = "user_management"
            st.rerun()
