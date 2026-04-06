"""Return note list, detail (PO lines, reason), submit, Head of Purchasing approval."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session, joinedload

from models import (
    AppUser,
    DocumentStatus,
    InventoryReceive,
    PurchaseOrder,
    PurchaseRequest,
    PurchaseRequestItem,
    ReturnNote,
    StatusActionPermission,
)
from utils import list_row_matches_filter

SS_RN_SCREEN = "rn_workspace_screen"
SS_RN_ID = "rn_workspace_rn_id"
SS_RN_LIST_DF = "rn_list_selection_df"
PMS_RN_JUST_CREATED = "pms_rn_just_created"


def _rn_reason_reset_key(rn_id: int) -> str:
    """If set, clear the reason widget key on the next detail render (before widgets run)."""
    return f"_rn_reset_reason_{rn_id}"


def _rn_status_key(status: str | None) -> str:
    return (status or "").strip().lower()


def get_rn_actions(session: Session, role_id: int, status_code: str) -> List[StatusActionPermission]:
    return (
        session.query(StatusActionPermission)
        .filter_by(
            document_type="RN",
            status_code=_rn_status_key(status_code),
            role_id=role_id,
            is_allowed=True,
        )
        .all()
    )


def _rn_status_label(session: Session, status_code: str) -> str:
    code = (status_code or "").strip().lower()
    row = session.query(DocumentStatus).filter_by(document_type="RN", status_code=code).first()
    if row:
        return row.status_label
    return (status_code or "—").replace("_", " ").title()


def _rn_list_selected_indices(event: Any) -> List[int]:
    if event is None:
        return []
    sel = getattr(event, "selection", None)
    if sel is None and isinstance(event, dict):
        sel = event.get("selection")
    if sel is None:
        return []
    if isinstance(sel, dict):
        return list(sel.get("rows") or [])
    return list(getattr(sel, "rows", None) or [])


def _go_rn_list() -> None:
    st.session_state[SS_RN_SCREEN] = "list"
    st.session_state.pop(SS_RN_ID, None)
    st.session_state.pop(SS_RN_LIST_DF, None)


def _go_rn_detail(rn_id: int) -> None:
    st.session_state[SS_RN_SCREEN] = "detail"
    st.session_state[SS_RN_ID] = rn_id


def _can_edit_rn_reason(user: AppUser, rn: ReturnNote) -> bool:
    if str(rn.status or "").lower() != "draft":
        return False
    return bool(user.role.is_master or user.id == rn.requester_id)


def render_rn_workspace(session: Session, user: AppUser, menu_rows: dict) -> None:
    mv = menu_rows.get("inventory_return")
    if not mv or not mv.can_view:
        st.error("No access.")
        return
    flash = st.session_state.pop(PMS_RN_JUST_CREATED, None)
    if flash:
        st.success(flash)
    st.session_state.setdefault(SS_RN_SCREEN, "list")
    screen = st.session_state[SS_RN_SCREEN]
    if screen == "detail":
        rn_id = st.session_state.get(SS_RN_ID)
        if not rn_id:
            _go_rn_list()
            st.rerun()
            return
        _render_rn_detail(session, user, int(rn_id))
    else:
        _render_rn_list(session, user)


def _render_rn_list(session: Session, user: AppUser) -> None:
    st.subheader("Return notes")
    st.caption("Return documents linked to a closed inventory receipt. Open a row for items, reason, and workflow.")
    rns = session.query(ReturnNote).order_by(ReturnNote.id.desc()).limit(200).all()
    if not rns:
        st.info("No return notes.")
        return
    statuses = sorted({r.status for r in rns})
    fc1, fc2 = st.columns([2.2, 1])
    with fc1:
        search = st.text_input(
            "Search",
            "",
            key="rn_list_search_q",
            placeholder="RN number, IR id, status, reason…",
        )
    with fc2:
        status_pick = st.selectbox(
            "Status",
            ["All"] + statuses,
            key="rn_list_status_f",
        )
    rn_ids: List[int] = []
    rows_out: List[Dict[str, Any]] = []
    for r in rns:
        reason = r.reason or ""
        if not list_row_matches_filter(
            search,
            status_pick,
            r.status,
            r.rn_number,
            str(r.ir_id),
            r.status,
            reason,
        ):
            continue
        rn_ids.append(r.id)
        rows_out.append(
            {
                "RN": r.rn_number,
                "IR id": r.ir_id,
                "Status": _rn_status_label(session, r.status),
            }
        )
    if not rows_out:
        st.info("No return notes match your search or status filter.")
        return
    st.caption("Click a row to open the return document (line items, reason, submit / approve).")
    df = pd.DataFrame(rows_out)
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key=SS_RN_LIST_DF,
    )
    ev = st.session_state.get(SS_RN_LIST_DF)
    for raw in _rn_list_selected_indices(ev):
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(rn_ids):
            _go_rn_detail(rn_ids[idx])
            st.session_state.pop(SS_RN_LIST_DF, None)
            st.rerun()
        break


def _render_rn_detail(session: Session, user: AppUser, rn_id: int) -> None:
    from po_ui import _po_line_rows, _requester_display

    rn = (
        session.query(ReturnNote)
        .options(
            joinedload(ReturnNote.inventory_receive)
            .joinedload(InventoryReceive.purchase_order)
            .joinedload(PurchaseOrder.purchase_request)
            .joinedload(PurchaseRequest.items)
            .joinedload(PurchaseRequestItem.supplier),
            joinedload(ReturnNote.inventory_receive)
            .joinedload(InventoryReceive.purchase_order)
            .joinedload(PurchaseOrder.pr_line_item)
            .joinedload(PurchaseRequestItem.supplier),
        )
        .filter_by(id=rn_id)
        .first()
    )
    if not rn:
        st.error("Return note not found.")
        _go_rn_list()
        st.rerun()
        return

    if st.button("← Back to list"):
        _go_rn_list()
        st.rerun()

    ir = rn.inventory_receive
    po = ir.purchase_order if ir else None
    pr = po.purchase_request if po else None

    st.markdown(f"## Return note `{rn.rn_number}`")
    st.caption(
        f"Status: **{_rn_status_label(session, rn.status)}** · "
        f"Receipt **{ir.ir_number if ir else '—'}** · PO **{po.po_number if po else '—'}** · "
        f"PR **{pr.pr_number if pr else '—'}**"
    )

    st.markdown("### Requester")
    if pr:
        st.write(_requester_display(pr))
    else:
        rq = session.get(AppUser, rn.requester_id)
        if rq and rq.student:
            nm = f"{rq.student.first_name} {rq.student.last_name}".strip()
            st.write(nm or rq.email or "—")
        else:
            st.caption(rq.email if rq else "—")

    st.markdown("### Items (from purchase order / receipt)")
    line_dicts = _po_line_rows(po) if po else []
    if line_dicts:
        show = []
        for r in line_dicts:
            show.append(
                {
                    "Item": r.get("Item"),
                    "Description": r.get("Description"),
                    "Qty": r.get("Qty"),
                    "Unit price": r.get("Unit price"),
                    "Subtotal": r.get("Subtotal"),
                    "Supplier": r.get("Supplier"),
                }
            )
        st.dataframe(
            pd.DataFrame(show),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Qty": st.column_config.NumberColumn(format="%.4g"),
                "Unit price": st.column_config.NumberColumn(format="%.2f"),
                "Subtotal": st.column_config.NumberColumn(format="%.2f"),
            },
        )
    else:
        st.caption("No line items found for this receipt.")

    st.markdown("### Return reason")
    rk = f"rn_d_reason_{rn.id}"
    # Streamlit forbids mutating session_state[rk] after st.text_area(..., key=rk) runs in the same script run.
    if st.session_state.pop(_rn_reason_reset_key(rn.id), False):
        st.session_state.pop(rk, None)
    if _can_edit_rn_reason(user, rn):
        # Do not pass value= with key= — Streamlit resets the widget each run and breaks save/submit.
        if rk not in st.session_state:
            st.session_state[rk] = rn.reason or ""
        st.text_area(
            "Explain what is being returned and why (required before submit).",
            height=160,
            key=rk,
        )
        sc1, sc2 = st.columns(2)
        with sc1:
            if st.button("Save reason", key=f"rn_save_reason_{rn.id}"):
                row = session.get(ReturnNote, rn.id)
                if row:
                    txt = str(st.session_state.get(rk, "") or "").strip()
                    row.reason = txt or None
                    row.updated_at = datetime.utcnow()
                    session.commit()
                    st.rerun()
        with sc2:
            if st.button("Cancel", key=f"rn_cancel_{rn.id}"):
                st.session_state[_rn_reason_reset_key(rn.id)] = True
                _go_rn_list()
                st.rerun()
    else:
        st.write((rn.reason or "").strip() or "—")

    st.markdown("### Actions")
    status_l = _rn_status_key(rn.status)
    role_id = user.role.id if user.role is not None else user.role_id
    if status_l == "draft" and _can_edit_rn_reason(user, rn):
        st.caption("**Draft** — save your reason, then submit for Head of Purchasing approval.")
    elif status_l == "draft":
        st.caption("Only the **requester** or **Master** can edit the reason and submit this draft return.")
    elif status_l == "submitted":
        st.caption("Awaiting **Head of Purchasing** (or **Master**) approval.")
    elif status_l == "approved":
        st.caption(
            "**Approved** — use **Completed** when the return is fully done (closes the note), "
            "or **Cancel** to void it (status becomes rejected)."
        )
    elif status_l == "closed":
        st.caption("This return note is **completed** and closed.")
    elif status_l == "rejected":
        st.caption("This return was rejected.")

    actions = get_rn_actions(session, role_id, status_l)

    def _do_submit() -> None:
        row = session.get(ReturnNote, rn.id)
        if not row:
            return
        merged = str(st.session_state.get(rk, row.reason or "") or "").strip()
        if not merged:
            st.error("Please add a **return reason** before submitting.")
            return
        row.reason = merged
        row.status = "submitted"
        row.updated_at = datetime.utcnow()
        session.commit()
        st.session_state[_rn_reason_reset_key(rn.id)] = True
        st.rerun()

    _primary_actions = frozenset({"submit", "approve", "complete"})
    for sap in sorted(
        actions,
        key=lambda x: (0 if x.action_key in _primary_actions else 1, x.action_key != "complete", x.button_label),
    ):
        btn_type = "primary" if sap.action_key in _primary_actions else "secondary"
        if st.button(sap.button_label, key=f"rn_act_{rn.id}_{sap.action_key}", type=btn_type):
            row = session.get(ReturnNote, rn.id)
            if not row or not sap.next_status:
                return
            if sap.action_key == "submit":
                _do_submit()
                return
            row.status = sap.next_status
            row.updated_at = datetime.utcnow()
            session.commit()
            st.session_state[_rn_reason_reset_key(rn.id)] = True
            st.rerun()

    if not actions and status_l == "draft" and _can_edit_rn_reason(user, rn):
        st.caption("Using built-in actions (database permissions will be synced on next app restart).")
        if st.button("Submit for HoP approval", type="primary", key=f"rn_fb_submit_{rn.id}"):
            _do_submit()

    if not actions and status_l == "approved":
        rname = user.role.role_name if user.role else ""
        if rname in ("requester", "master", "head_of_purchasing", "purchasing_team"):
            st.caption("Using built-in **Completed** / **Cancel** (sync permissions on next app restart if needed).")
            fc1, fc2 = st.columns(2)
            with fc1:
                if st.button("Completed", type="primary", key=f"rn_fb_complete_{rn.id}"):
                    row = session.get(ReturnNote, rn.id)
                    if row:
                        row.status = "closed"
                        row.updated_at = datetime.utcnow()
                        session.commit()
                        st.session_state[_rn_reason_reset_key(rn.id)] = True
                        st.rerun()
            with fc2:
                if st.button("Cancel", type="secondary", key=f"rn_fb_void_{rn.id}"):
                    row = session.get(ReturnNote, rn.id)
                    if row:
                        row.status = "rejected"
                        row.updated_at = datetime.utcnow()
                        session.commit()
                        st.session_state[_rn_reason_reset_key(rn.id)] = True
                        st.rerun()
