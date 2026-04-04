"""Purchase order list and basic detail."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session, joinedload

from models import AppUser, PurchaseOrder, PurchaseRequest


def render_po_workspace(session: Session, user: AppUser, menu_rows: dict) -> None:
    mv = menu_rows.get("purchase_order")
    if not mv or not mv.can_view:
        st.error("No access.")
        return
    st.subheader("Purchase orders")
    q = session.query(PurchaseOrder).options(joinedload(PurchaseOrder.purchase_request)).order_by(PurchaseOrder.id.desc())
    pos = q.limit(100).all()
    if not pos:
        st.info("No purchase orders. Create from an approved PR (**Create PO** on the PR detail page).")
        return
    rows = []
    for po in pos:
        prn = po.purchase_request.pr_number if po.purchase_request else "?"
        rows.append({"PO": po.po_number, "PR": prn, "Status": po.status})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
