"""Purchase order list with PR line details from linked purchase request."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session, joinedload

from models import AppUser, InventoryReceive, PurchaseOrder, PurchaseRequest, PurchaseRequestItem
from pr_ui import SS_PR_ID, SS_SCREEN
from utils import list_row_matches_filter, next_document_number


def _requester_display(pr: PurchaseRequest | None) -> str:
    if not pr or not pr.requester:
        return "—"
    stu = pr.requester.student
    if stu:
        name = f"{stu.first_name} {stu.last_name}".strip()
        if name:
            return name
    return pr.requester.email or "—"


def _purchasing_round_display(pr: PurchaseRequest | None) -> str:
    if not pr or not pr.purchasing_round:
        return "—"
    return pr.purchasing_round.round_name


def _po_line_rows(po: PurchaseOrder) -> List[Dict[str, Any]]:
    pr = po.purchase_request
    req_name = _requester_display(pr)
    rnd = _purchasing_round_display(pr)
    if not pr:
        return [
            {
                "po_id": po.id,
                "PO": po.po_number,
                "PR": "—",
                "pr_id": None,
                "Purchasing round": rnd,
                "PO status": po.status,
                "Requester": "—",
                "Item": "—",
                "Description": "—",
                "Qty": None,
                "Unit price": None,
                "Subtotal": None,
                "Supplier": "—",
            }
        ]
    if po.pr_line_item_id is not None:
        lit = next((x for x in pr.items if x.id == po.pr_line_item_id), None)
        items_sorted = [lit] if lit is not None else []
    else:
        items_sorted = sorted(pr.items, key=lambda x: x.item_no)
    if not items_sorted:
        return [
            {
                "po_id": po.id,
                "PO": po.po_number,
                "PR": pr.pr_number,
                "pr_id": pr.id,
                "Purchasing round": rnd,
                "PO status": po.status,
                "Requester": req_name,
                "Item": "—",
                "Description": "—",
                "Qty": None,
                "Unit price": None,
                "Subtotal": None,
                "Supplier": "—",
            }
        ]
    out: List[Dict[str, Any]] = []
    for it in items_sorted:
        sup = it.supplier.supplier_name if it.supplier else "—"
        out.append(
            {
                "po_id": po.id,
                "PO": po.po_number,
                "PR": pr.pr_number,
                "pr_id": pr.id,
                "Purchasing round": rnd,
                "PO status": po.status,
                "Requester": req_name,
                "Item": it.item_no,
                "Description": it.description,
                "Qty": float(it.qty),
                "Unit price": float(it.unit_price),
                "Subtotal": float(it.sub_total),
                "Supplier": sup,
            }
        )
    return out


_PO_GROUP_COLUMNS = ["PO", "PR", "Purchasing round", "PO status", "Requester", "Supplier"]


def _purchasing_round_filter_options(pos: List[PurchaseOrder]) -> List[str]:
    labels: set[str] = set()
    for po in pos:
        pr = po.purchase_request
        if pr and pr.purchasing_round:
            labels.add(pr.purchasing_round.round_name)
        else:
            labels.add("—")
    return sorted(labels, key=lambda x: (x != "—", x.lower()))


def _po_line_column_config() -> dict:
    return {
        "Qty": st.column_config.NumberColumn(format="%.4g"),
        "Unit price": st.column_config.NumberColumn(format="%.2f"),
        "Subtotal": st.column_config.NumberColumn(format="%.2f"),
    }


def _po_open_status_for_ir(status: str) -> bool:
    return (status or "").strip().lower() == "open"


def _first_ir_by_po_ids(session: Session, po_ids: List[int]) -> Dict[int, InventoryReceive]:
    if not po_ids:
        return {}
    out: Dict[int, InventoryReceive] = {}
    for ir in (
        session.query(InventoryReceive)
        .filter(InventoryReceive.po_id.in_(po_ids))
        .order_by(InventoryReceive.id.asc())
        .all()
    ):
        out.setdefault(ir.po_id, ir)
    return out


def _try_create_ir_for_po(session: Session, user: AppUser, po_id: int) -> tuple[bool, str, int | None]:
    po = session.get(PurchaseOrder, po_id)
    if po is None:
        return False, "Purchase order not found.", None
    if not _po_open_status_for_ir(po.status):
        return False, "IR can only be created when the PO status is **open**.", None
    existing = session.query(InventoryReceive).filter_by(po_id=po.id).first()
    if existing is not None:
        return False, f"This PO already has receipt **{existing.ir_number}**.", None
    ir = InventoryReceive(
        ir_number=next_document_number(session, "IR"),
        po_id=po.id,
        received_by_id=user.id,
        status="open",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(ir)
    session.commit()
    return True, ir.ir_number, ir.id


def _render_po_dataframe_grouped(df: pd.DataFrame, group_col: str) -> None:
    cfg = _po_line_column_config()
    if group_col == "None":
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config=cfg,
        )
        return

    work = df.copy()
    work["_g"] = work[group_col].apply(lambda x: "—" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x))
    work = work.sort_values(by=["_g", "PO", "PR", "Item"], kind="mergesort", na_position="last")
    n_groups = work["_g"].nunique()
    expand = n_groups <= 15
    for val, chunk in work.groupby("_g", sort=True):
        title = val if str(val) != "nan" else "—"
        with st.expander(f"{group_col}: **{title}** ({len(chunk)} line(s))", expanded=expand):
            disp = chunk.drop(columns=["_g", group_col], errors="ignore").reset_index(drop=True)
            st.dataframe(
                disp,
                hide_index=True,
                use_container_width=True,
                column_config=cfg,
            )


def render_po_workspace(session: Session, user: AppUser, menu_rows: dict) -> None:
    mv = menu_rows.get("purchase_order")
    if not mv or not mv.can_view:
        st.error("No access.")
        return
    st.subheader("Purchase orders")
    q = (
        session.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.purchase_request)
            .joinedload(PurchaseRequest.requester)
            .joinedload(AppUser.student),
            joinedload(PurchaseOrder.purchase_request).joinedload(PurchaseRequest.purchasing_round),
            joinedload(PurchaseOrder.purchase_request)
            .joinedload(PurchaseRequest.items)
            .joinedload(PurchaseRequestItem.supplier),
            joinedload(PurchaseOrder.pr_line_item).joinedload(PurchaseRequestItem.supplier),
        )
        .order_by(PurchaseOrder.id.desc())
        .limit(200)
    )
    pos = q.all()
    if not pos:
        st.info("No purchase orders. Open an approved PR and use **Create PO** on each line that needs a PO.")
        return
    statuses = sorted({po.status for po in pos})
    round_opts = _purchasing_round_filter_options(pos)
    fc1, fc2 = st.columns([2.2, 1])
    with fc1:
        search = st.text_input(
            "Search",
            "",
            key="po_list_search_q",
            placeholder="PO, PR, purchasing round, requester, description, supplier…",
        )
    with fc2:
        status_pick = st.selectbox(
            "PO status",
            ["All"] + statuses,
            key="po_list_status_f",
        )
    fc3, fc4 = st.columns([1, 1])
    with fc3:
        round_pick = st.selectbox(
            "Purchasing round",
            ["All"] + round_opts,
            key="po_round_filter_f",
        )
    with fc4:
        group_pick = st.selectbox(
            "Group by",
            ["None"] + _PO_GROUP_COLUMNS,
            key="po_group_by_col",
        )

    line_rows: List[Dict[str, Any]] = []
    for po in pos:
        for row in _po_line_rows(po):
            if round_pick != "All" and row["Purchasing round"] != round_pick:
                continue
            if not list_row_matches_filter(
                search,
                status_pick,
                po.status,
                row["PO"],
                row["PR"],
                row["Purchasing round"],
                row["PO status"],
                row["Requester"],
                str(row["Item"]),
                row["Description"],
                str(row["Qty"] or ""),
                str(row["Unit price"] or ""),
                str(row["Subtotal"] or ""),
                row["Supplier"],
            ):
                continue
            line_rows.append(row)

    if not line_rows:
        st.info("No purchase order lines match your search or filters.")
        return

    df_full = pd.DataFrame(line_rows)
    mv_pr = menu_rows.get("purchase_request")
    mv_ir = menu_rows.get("inventory_receipt")

    if group_pick == "None":
        err_flash = st.session_state.pop("po_ir_create_error", None)
        if err_flash:
            st.error(err_flash)
        po_ids_list = list({int(r["po_id"]) for r in line_rows})
        ir_by_po = _first_ir_by_po_ids(session, po_ids_list)
        st.caption(
            "Each row is one PR line on the PO. Use **Open PR** and **Create IR** on that row "
            "(one receipt per PO; other lines for the same PO show the IR number instead of **Create IR**). "
            "Attach files for an IR on **Inventory receipt**."
        )
        hdr_w = [0.68, 0.68, 0.92, 0.58, 0.74, 0.34, 1.02, 0.38, 0.44, 0.48, 0.76, 1.12]
        h = st.columns(hdr_w)
        for i, lab in enumerate(
            [
                "PO",
                "PR",
                "Round",
                "PO status",
                "Requester",
                "#",
                "Description",
                "Qty",
                "Unit",
                "Subtotal",
                "Supplier",
                "Actions",
            ]
        ):
            h[i].markdown(f"**{lab}**")

        for i, row in enumerate(line_rows):
            po_id = int(row["po_id"])
            existing = ir_by_po.get(po_id)
            cols = st.columns(hdr_w)
            cols[0].markdown(row["PO"])
            cols[1].markdown(row["PR"])
            cols[2].markdown(row["Purchasing round"])
            cols[3].markdown(row["PO status"])
            cols[4].markdown(row["Requester"])
            cols[5].markdown(f"<div style='text-align:center'>{row['Item']}</div>", unsafe_allow_html=True)
            desc = str(row["Description"] if row["Description"] is not None else "—")
            if len(desc) > 48:
                desc = desc[:45] + "…"
            cols[6].markdown(desc)
            cols[7].markdown(f"<div style='text-align:center'>{row['Qty'] if row['Qty'] is not None else '—'}</div>", unsafe_allow_html=True)
            cols[8].markdown(
                f"<div style='text-align:center'>{row['Unit price']:.2f}</div>"
                if row["Unit price"] is not None
                else "<div style='text-align:center'>—</div>",
                unsafe_allow_html=True,
            )
            cols[9].markdown(
                f"<div style='text-align:center'>{row['Subtotal']:.2f}</div>"
                if row["Subtotal"] is not None
                else "<div style='text-align:center'>—</div>",
                unsafe_allow_html=True,
            )
            cols[10].markdown(row["Supplier"])
            act = cols[11]
            with act:
                o1, o2 = st.columns(2)
                with o1:
                    pr_raw = row.get("pr_id")
                    pr_ok = pr_raw is not None and not (isinstance(pr_raw, float) and pd.isna(pr_raw))
                    pr_id_int: int | None
                    try:
                        pr_id_int = int(pr_raw) if pr_ok else None
                    except (TypeError, ValueError):
                        pr_id_int = None
                    if mv_pr and mv_pr.can_view and pr_id_int is not None:
                        if st.button("Open PR", key=f"po_open_pr_{po_id}_{i}", use_container_width=True):
                            st.session_state[SS_PR_ID] = pr_id_int
                            st.session_state[SS_SCREEN] = "detail"
                            st.session_state["pms_navigate_to_page"] = "purchase_request"
                            st.rerun()
                    else:
                        st.caption("—")
                with o2:
                    if mv_ir and mv_ir.can_view:
                        if existing is not None:
                            st.caption(f"**{existing.ir_number}**")
                        elif _po_open_status_for_ir(str(row["PO status"])):
                            if st.button("Create IR", key=f"po_create_ir_{po_id}_{i}", use_container_width=True, type="primary"):
                                ok, info, new_ir_id = _try_create_ir_for_po(session, user, po_id)
                                if ok:
                                    import ir_ui

                                    st.session_state[ir_ui.SS_IR_SCREEN] = "detail"
                                    st.session_state[ir_ui.SS_IR_ID] = new_ir_id
                                    st.session_state["pms_navigate_to_page"] = "inventory_receipt"
                                else:
                                    st.session_state["po_ir_create_error"] = info
                                st.rerun()
                        else:
                            st.caption("—")
                    else:
                        st.caption("—")
    else:
        _render_po_dataframe_grouped(
            df_full.drop(columns=["pr_id", "po_id"], errors="ignore"),
            group_pick,
        )
        st.caption(
            f"Grouped by **{group_pick}**. Set **Group by** to **None** for the line table with **Open PR** / **Create IR** buttons."
        )
