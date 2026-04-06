"""
Purchasing Management System — Streamlit entrypoint.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session, joinedload

from auth import (
    SESSION_LAST_LOGIN_DISPLAY,
    attempt_login,
    clear_auth_session,
    get_current_user,
    is_logged_in,
    set_session_from_user,
)
from budget_ui import render_budget_management
from database import (
    engine,
    ensure_budget_management_menu,
    ensure_ir_closed_document_status,
    ensure_ir_ready_for_pickup_document_status,
    ensure_pr_reviewed_hop_actions,
    ensure_rn_cancelled_document_status,
    ensure_rn_workflow_permissions,
    get_session,
    migrate_sqlite_schema,
)
from dashboard import render_dashboard
from models import AppUser, Base, MenuVisibility
from po_ui import render_po_workspace
from pr_ui import render_pr_workspace
from ir_ui import render_ir_workspace
from rn_ui import render_rn_workspace
from seed import seed_if_empty
from user_management import render_user_management


def _menu_dict(session: Session, role_id: int) -> dict:
    return {r.menu_key: r for r in session.query(MenuVisibility).filter_by(role_id=role_id).all()}


def _app_shell_css() -> None:
    """Hide sidebar; optional top spacing for main app (after login)."""
    st.markdown(
        """
<style>
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
button[kind="header"] { display: none !important; }
</style>
""",
        unsafe_allow_html=True,
    )


def _login_screen_css() -> None:
    st.markdown(
        """
<style>
html, body,
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main .block-container {
  background-color: #300060 !important;
}
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"] {
  visibility: hidden !important;
  height: 0 !important;
  min-height: 0 !important;
  max-height: 0 !important;
  overflow: hidden !important;
}
section[data-testid="stSidebar"] {
  display: none !important;
}
footer[data-testid="stFooter"] {
  visibility: hidden !important;
  height: 0 !important;
}
.block-container {
  max-width: 440px !important;
  margin-left: auto !important;
  margin-right: auto !important;
  padding-top: min(12vh, 6rem) !important;
  padding-bottom: 4rem !important;
  min-height: 88vh !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
}
.login-welcome {
  color: #ffffff !important;
  font-family: Georgia, "Times New Roman", Times, serif !important;
  font-size: 1.85rem !important;
  font-weight: 400 !important;
  text-align: center !important;
  margin: 0 0 2rem 0 !important;
  letter-spacing: 0.02em;
}
.login-row-label {
  color: #ffffff !important;
  font-family: Georgia, "Times New Roman", Times, serif !important;
  font-size: 1rem !important;
  text-align: right !important;
  padding: 0.65rem 0.75rem 0 0 !important;
  line-height: 1.4 !important;
}
[data-testid="stTextInput"] label,
[data-testid="stTextInput"] [data-testid="stWidgetLabel"] {
  display: none !important;
}
[data-testid="stTextInput"] input {
  background-color: #ffffff !important;
  color: #1a1a1a !important;
  border: 1px solid #e8e8e8 !important;
  border-radius: 2px !important;
  font-family: system-ui, -apple-system, sans-serif !important;
}
[data-testid="stTextInput"] > div > div {
  background-color: #ffffff !important;
  border-radius: 2px !important;
}
form[data-testid="stForm"] button[type="submit"],
[data-testid="stFormSubmitButton"] button {
  background-color: #F7DC6F !important;
  color: #ffffff !important;
  border: none !important;
  width: 100% !important;
  font-family: system-ui, -apple-system, sans-serif !important;
  font-weight: 600 !important;
  font-size: 1.05rem !important;
  padding: 0.7rem 1rem !important;
  border-radius: 2px !important;
  margin-top: 0.5rem !important;
}
form[data-testid="stForm"] button[type="submit"]:hover,
[data-testid="stFormSubmitButton"] button:hover {
  background-color: #e8cf66 !important;
  color: #ffffff !important;
}
[data-testid="stNotificationContentError"],
[data-testid="stAlert"] {
  background-color: rgba(0,0,0,0.25) !important;
  color: #fff !important;
  border: 1px solid rgba(255,255,255,0.35) !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="TECHIN — Purchasing", layout="wide", initial_sidebar_state="collapsed")
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema()

    db = get_session()
    try:
        if seed_if_empty(db):
            db.commit()
        ensure_budget_management_menu(db)
        ensure_ir_closed_document_status(db)
        ensure_ir_ready_for_pickup_document_status(db)
        ensure_rn_cancelled_document_status(db)
        ensure_rn_workflow_permissions(db)
        ensure_pr_reviewed_hop_actions(db)
        if not is_logged_in():
            _login_screen_css()
            st.markdown('<p class="login-welcome">Welcome TECHIN!</p>', unsafe_allow_html=True)
            with st.form("login"):
                e1, e2 = st.columns([0.92, 1.6])
                with e1:
                    st.markdown('<div class="login-row-label">Email</div>', unsafe_allow_html=True)
                with e2:
                    email = st.text_input("email", key="login_email", label_visibility="collapsed", placeholder="")
                p1, p2 = st.columns([0.92, 1.6])
                with p1:
                    st.markdown('<div class="login-row-label">Password</div>', unsafe_allow_html=True)
                with p2:
                    password = st.text_input(
                        "password",
                        type="password",
                        key="login_password",
                        label_visibility="collapsed",
                        placeholder="",
                    )
                if st.form_submit_button("Log in"):
                    user = attempt_login(db, email, password)
                    if user:
                        set_session_from_user(user)
                        st.session_state[SESSION_LAST_LOGIN_DISPLAY] = user.email
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")
            return

        user = get_current_user(db)
        if not user or not user.is_active:
            clear_auth_session()
            st.error("Session expired.")
            st.rerun()
            return

        user = (
            db.query(AppUser)
            .options(joinedload(AppUser.role), joinedload(AppUser.student))
            .filter_by(id=user.id)
            .first()
        )

        menu = _menu_dict(db, user.role.id)

        nav_labels = {
            "dashboard": "Dashboard",
            "budget_management": "Budget management",
            "purchase_request": "Purchase requests",
            "purchase_order": "Purchase orders",
            "inventory_receipt": "Inventory receipt",
            "inventory_return": "Inventory return",
            "user_management": "User management",
        }
        page_keys = [
            "dashboard",
            "purchase_request",
            "purchase_order",
            "inventory_receipt",
            "inventory_return",
        ]
        mv_budget = menu.get("budget_management")
        if mv_budget and mv_budget.can_view:
            page_keys.insert(1, "budget_management")
        if user.role.is_master:
            page_keys.append("user_management")

        _app_shell_css()

        nav_jump = st.session_state.pop("pms_navigate_to_page", None)
        if nav_jump is not None and nav_jump in page_keys:
            st.session_state["pms_top_nav"] = nav_jump

        top_user, top_out = st.columns([5, 1])
        with top_user:
            st.markdown(f"**{user.email}** · _{user.role.role_name.replace('_', ' ')}_")
        with top_out:
            if st.button("Log out", key="pms_logout_top", use_container_width=True):
                clear_auth_session()
                st.rerun()

        page = st.radio(
            "Navigate",
            page_keys,
            format_func=lambda x: nav_labels[x],
            horizontal=True,
            label_visibility="collapsed",
            key="pms_top_nav",
        )
        st.divider()

        mv_pr = menu.get("purchase_request")
        if page == "user_management":
            if not user.role.is_master:
                st.error("Master only.")
            else:
                render_user_management(db)
        elif page == "budget_management":
            if not mv_budget or not mv_budget.can_view:
                st.error("Access denied.")
            else:
                render_budget_management(db, user)
        elif page == "dashboard":
            render_dashboard(db, user)
        elif page == "purchase_request":
            render_pr_workspace(db, user, menu)
        elif page == "purchase_order":
            render_po_workspace(db, user, menu)
        elif page == "inventory_receipt":
            render_ir_workspace(db, user, menu)
        elif page == "inventory_return":
            render_rn_workspace(db, user, menu)
        else:
            render_dashboard(db, user)

    finally:
        db.close()


if __name__ == "__main__":
    main()
