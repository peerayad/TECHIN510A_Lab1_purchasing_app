"""Inventory receipt (IR) list and simple status view."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session, joinedload

from models import AppUser, InventoryReceive, PurchaseOrder


def render_ir_workspace(session: Session, user: AppUser, menu_rows: dict) -> None:
    mv = menu_rows.get("inventory_receipt")
    if not mv or not mv.can_view:
        st.error("No access.")
        return
    st.subheader("Inventory receipts")
    rows = (
        session.query(InventoryReceive)
        .options(joinedload(InventoryReceive.purchase_order))
        .order_by(InventoryReceive.id.desc())
        .limit(100)
        .all()
    )
    if not rows:
        st.info("No inventory receipts.")
        return
    data = []
    for ir in rows:
        po = ir.purchase_order
        data.append(
            {
                "IR": ir.ir_number,
                "PO": po.po_number if po else "—",
                "Status": ir.status,
                "PO doc": ir.po_document_ok,
                "Delivery": ir.delivery_note_ok,
                "Invoice": ir.invoice_ok,
            }
        )
    st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)
    st.caption("Extend with verify / accept workflows and forms as needed.")
