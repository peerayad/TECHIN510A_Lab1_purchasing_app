"""Return note list and placeholder detail."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from models import AppUser, ReturnNote


def render_rn_workspace(session: Session, user: AppUser, menu_rows: dict) -> None:
    mv = menu_rows.get("inventory_return")
    if not mv or not mv.can_view:
        st.error("No access.")
        return
    st.subheader("Return notes")
    rns = session.query(ReturnNote).order_by(ReturnNote.id.desc()).limit(100).all()
    if not rns:
        st.info("No return notes.")
        return
    st.dataframe(
        pd.DataFrame([{"RN": r.rn_number, "IR id": r.ir_id, "Status": r.status} for r in rns]),
        hide_index=True,
        use_container_width=True,
    )
    st.caption("Extend with create / approve / close workflows as needed.")
