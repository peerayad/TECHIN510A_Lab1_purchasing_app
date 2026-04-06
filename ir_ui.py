"""Inventory receipt list, row navigation to detail (lines, requester, checklist, files)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session, joinedload

from database import DATA_DIR
from models import (
    AppUser,
    DocumentStatus,
    IRAttachment,
    IRStatusHistory,
    InventoryReceive,
    PurchaseOrder,
    PurchaseRequest,
    PurchaseRequestItem,
    ReturnNote,
    StudentList,
)
from utils import (
    list_row_matches_filter,
    log_ir_status_change,
    log_rn_status_change,
    next_document_number,
    save_ir_attachment_file,
)

from pms_ui import pms_button_mark

SS_IR_SCREEN = "ir_workspace_screen"
SS_IR_ID = "ir_workspace_ir_id"
SS_IR_LIST_DF = "ir_list_selection_df"

_IR_UPLOAD_MAX_BYTES = 15 * 1024 * 1024


def _can_edit_ir_checklist(user: AppUser) -> bool:
    return bool(user.role.is_master or user.role.role_name == "purchasing_team")


def _can_mark_ready_for_pickup(user: AppUser) -> bool:
    return bool(user.role.is_master or user.role.role_name == "purchasing_team")


def _ir_status_key(code: str | None) -> str:
    return str(code or "").strip().lower()


def _checklist_complete_for_pickup(ir: InventoryReceive) -> bool:
    return bool(ir.po_document_ok and ir.delivery_note_ok and ir.invoice_ok)


def _user_is_pr_requester(user: AppUser, pr: PurchaseRequest | None) -> bool:
    return pr is not None and pr.requester_id == user.id


def _ir_status_label(session: Session, status_code: str) -> str:
    row = (
        session.query(DocumentStatus)
        .filter_by(document_type="IR", status_code=(status_code or "").strip().lower())
        .first()
    )
    if row:
        return row.status_label
    return (status_code or "—").replace("_", " ").title()


def _try_create_return_note(
    session: Session, ir_id: int, pr: PurchaseRequest | None, user: AppUser
) -> Tuple[bool, str, int | None]:
    if pr is None:
        return False, "Missing purchase request.", None
    ir_row = session.get(InventoryReceive, ir_id)
    if ir_row is None:
        return False, "Receipt not found.", None
    if str(ir_row.status or "").lower() != "closed":
        return False, "Return notes can only be created for **closed** receipts.", None
    rn_number = next_document_number(session, "RN")
    note = ReturnNote(
        rn_number=rn_number,
        ir_id=ir_row.id,
        requester_id=pr.requester_id,
        status="draft",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(note)
    session.flush()
    log_rn_status_change(session, note.id, None, "draft", user.id)
    session.commit()
    session.refresh(note)
    return True, note.rn_number, note.id


def _ir_list_selected_indices(event: Any) -> List[int]:
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


def _go_ir_list() -> None:
    st.session_state[SS_IR_SCREEN] = "list"
    st.session_state.pop(SS_IR_ID, None)
    st.session_state.pop(SS_IR_LIST_DF, None)


def _go_ir_detail(ir_id: int) -> None:
    st.session_state[SS_IR_SCREEN] = "detail"
    st.session_state[SS_IR_ID] = ir_id


def render_ir_workspace(session: Session, user: AppUser, menu_rows: dict) -> None:
    mv = menu_rows.get("inventory_receipt")
    if not mv or not mv.can_view:
        st.error("No access.")
        return
    st.session_state.setdefault(SS_IR_SCREEN, "list")
    screen = st.session_state[SS_IR_SCREEN]
    if screen == "detail":
        ir_id = st.session_state.get(SS_IR_ID)
        if not ir_id:
            _go_ir_list()
            st.rerun()
            return
        _render_ir_detail(session, user, menu_rows, int(ir_id))
    else:
        _render_ir_list(session, user)


def _render_ir_list(session: Session, user: AppUser) -> None:
    from po_ui import _requester_display

    st.subheader("Inventory receipts")
    rows = (
        session.query(InventoryReceive)
        .options(
            joinedload(InventoryReceive.purchase_order)
            .joinedload(PurchaseOrder.purchase_request)
            .joinedload(PurchaseRequest.requester)
            .joinedload(AppUser.student),
            joinedload(InventoryReceive.attachments),
        )
        .order_by(InventoryReceive.id.desc())
        .limit(200)
        .all()
    )
    if not rows:
        st.info("No inventory receipts.")
        return
    statuses = sorted({ir.status for ir in rows})
    fc1, fc2 = st.columns([2.2, 1])
    with fc1:
        search = st.text_input(
            "Search",
            "",
            key="ir_list_search_q",
            placeholder="IR, PO, requester, status, checks…",
        )
    with fc2:
        status_pick = st.selectbox(
            "Status",
            ["All"] + statuses,
            key="ir_list_status_f",
        )
    filtered: list[InventoryReceive] = []
    for ir in rows:
        po = ir.purchase_order
        pr = po.purchase_request if po else None
        po_num = po.po_number if po else "—"
        req_nm = _requester_display(pr)
        n_files = len(ir.attachments)
        if not list_row_matches_filter(
            search,
            status_pick,
            ir.status,
            ir.ir_number,
            po_num,
            req_nm,
            ir.status,
            _ir_status_label(session, str(ir.status or "")),
            "yes" if ir.po_document_ok else "no",
            "yes" if ir.delivery_note_ok else "no",
            "yes" if ir.invoice_ok else "no",
            "yes" if ir.requester_accepted_at else "no",
            str(n_files),
        ):
            continue
        filtered.append(ir)

    if not filtered:
        st.info("No inventory receipts match your search or status filter.")
        return

    st.caption("Click a row in the table to open that receipt (line items, requester, checklist, attachments).")
    ir_ids: List[int] = []
    data: List[Dict[str, Any]] = []
    for ir in filtered:
        po = ir.purchase_order
        pr = po.purchase_request if po else None
        po_num = po.po_number if po else "—"
        ir_ids.append(ir.id)
        data.append(
            {
                "IR": ir.ir_number,
                "PO": po_num,
                "Requester": _requester_display(pr),
                "Status": _ir_status_label(session, str(ir.status or "")),
                "Files": len(ir.attachments),
                "PO doc": "✓" if ir.po_document_ok else "—",
                "Delivery": "✓" if ir.delivery_note_ok else "—",
                "Invoice": "✓" if ir.invoice_ok else "—",
                "Req. accepted": "✓" if ir.requester_accepted_at else "—",
            }
        )
    df = pd.DataFrame(data)
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={"Files": st.column_config.NumberColumn("Files", format="%d")},
        on_select="rerun",
        selection_mode="single-row",
        key=SS_IR_LIST_DF,
    )
    ev = st.session_state.get(SS_IR_LIST_DF)
    for raw in _ir_list_selected_indices(ev):
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(ir_ids):
            _go_ir_detail(ir_ids[idx])
            st.session_state.pop(SS_IR_LIST_DF, None)
            st.rerun()
        break


def _render_ir_detail(session: Session, user: AppUser, menu_rows: dict, ir_id: int) -> None:
    from po_ui import _po_line_rows

    ir = (
        session.query(InventoryReceive)
        .options(
            joinedload(InventoryReceive.attachments),
            joinedload(InventoryReceive.purchase_order)
            .joinedload(PurchaseOrder.purchase_request)
            .joinedload(PurchaseRequest.requester)
            .joinedload(AppUser.student),
            joinedload(InventoryReceive.purchase_order)
            .joinedload(PurchaseOrder.purchase_request)
            .joinedload(PurchaseRequest.items)
            .joinedload(PurchaseRequestItem.supplier),
            joinedload(InventoryReceive.purchase_order)
            .joinedload(PurchaseOrder.pr_line_item)
            .joinedload(PurchaseRequestItem.supplier),
            joinedload(InventoryReceive.requester_acceptor).joinedload(AppUser.student),
        )
        .filter_by(id=ir_id)
        .first()
    )
    if not ir:
        st.error("Inventory receipt not found.")
        _go_ir_list()
        st.rerun()
        return

    if st.button("← Back to list"):
        _go_ir_list()
        st.rerun()

    po = ir.purchase_order
    pr = po.purchase_request if po else None

    st.markdown(f"## Inventory receipt `{ir.ir_number}`")

    meta1, meta2 = st.columns(2)
    with meta1:
        st.text_input("PO number", value=po.po_number if po else "—", disabled=True, key=f"ir_d_po_{ir.id}")
        st.text_input("PR number", value=pr.pr_number if pr else "—", disabled=True, key=f"ir_d_pr_{ir.id}")
    with meta2:
        st.text_input(
            "Status",
            value=_ir_status_label(session, str(ir.status or "")),
            disabled=True,
            key=f"ir_d_st_{ir.id}",
        )
        ca = ir.created_at.strftime("%Y-%m-%d %H:%M UTC") if ir.created_at else "—"
        st.text_input("Created (UTC)", value=ca, disabled=True, key=f"ir_d_ca_{ir.id}")
        rb = session.get(AppUser, ir.received_by_id)
        rb_nm = "—"
        if rb and rb.student:
            rb_nm = f"{rb.student.first_name} {rb.student.last_name}".strip() or rb.email
        elif rb:
            rb_nm = rb.email or "—"
        st.text_input("Received by", value=rb_nm, disabled=True, key=f"ir_d_rb_{ir.id}")

    st.markdown("### Requester")
    if pr and pr.requester:
        rq = pr.requester.student
        nm = f"{rq.first_name} {rq.last_name}".strip() if rq else ""
        st.write(f"**{nm or pr.requester.email}** · `{pr.requester.email}`")
    else:
        st.caption("—")

    st.markdown("### Requester acceptance")
    ir_st = _ir_status_key(ir.status)
    if ir.requester_accepted_at:
        ts = ir.requester_accepted_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        acc = ir.requester_acceptor
        acc_lbl = ""
        if acc:
            stu = acc.student
            acc_lbl = f"{stu.first_name} {stu.last_name}".strip() if stu else ""
            if not acc_lbl:
                acc_lbl = acc.email or ""
        st.success(f"Inventory accepted **{ts}**" + (f" · {acc_lbl}" if acc_lbl else "") + ".")
    elif _user_is_pr_requester(user, pr) and ir_st == "ready_for_pickup":
        st.caption("Purchasing marked this receipt **ready to pick up**. Confirm after you collect the items.")
        if st.button("Accept inventory", type="primary", key=f"ir_d_req_accept_{ir.id}"):
            row = session.get(InventoryReceive, ir.id)
            if (
                row
                and _ir_status_key(row.status) == "ready_for_pickup"
                and not row.requester_accepted_at
                and pr
                and pr.requester_id == user.id
            ):
                old_st = row.status
                row.requester_accepted_at = datetime.utcnow()
                row.requester_accepted_by_id = user.id
                row.status = "closed"
                row.updated_at = datetime.utcnow()
                log_ir_status_change(session, row.id, old_st, "closed", user.id)
                session.commit()
                st.rerun()
    elif _user_is_pr_requester(user, pr) and ir_st == "open":
        st.info(
            "Waiting for **Purchasing** to mark this receipt **Ready to pick up**. "
            "After that, the **Accept inventory** button will appear here."
        )
    else:
        st.caption("Not accepted yet. Only the **requester** on this purchase request can accept (after pickup is ready).")

    st.markdown("### Return")
    ir_closed = str(ir.status or "").lower() == "closed"
    mv_rn = menu_rows.get("inventory_return")
    if ir_closed:
        if mv_rn and mv_rn.can_view and _user_is_pr_requester(user, pr):
            st.caption("Create a return note linked to this receipt (draft).")
            pms_button_mark("orange")
            if st.button("Return", type="secondary", key=f"ir_d_return_{ir.id}"):
                ok_rn, info, new_rn_id = _try_create_return_note(session, ir.id, pr, user)
                if ok_rn and new_rn_id is not None:
                    import rn_ui

                    st.session_state[rn_ui.SS_RN_SCREEN] = "detail"
                    st.session_state[rn_ui.SS_RN_ID] = new_rn_id
                    st.session_state[rn_ui.PMS_RN_JUST_CREATED] = f"Opened return note **{info}**."
                    st.session_state["pms_navigate_to_page"] = "inventory_return"
                    st.rerun()
                else:
                    st.error(info)
        elif mv_rn and mv_rn.can_view:
            st.caption("Only the **requester** on this purchase request can start a return.")
        else:
            st.caption("—")
    else:
        st.caption("The **Return** action is available after this receipt is **closed** (requester accepts inventory).")

    line_dicts = _po_line_rows(po) if po else []

    st.markdown("### Line items (from purchase order)")
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
        st.caption("No lines on this PO.")

    st.markdown("### Receiving checklist")
    if _can_edit_ir_checklist(user) and _ir_status_key(ir.status) == "open":
        st.caption("Tick each box when verified, then click **Save checklist**.")
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            v_po = st.checkbox(
                "PO document OK",
                value=bool(ir.po_document_ok),
                key=f"ir_d_chk_po_{ir.id}",
            )
        with cc2:
            v_dn = st.checkbox(
                "Delivery note OK",
                value=bool(ir.delivery_note_ok),
                key=f"ir_d_chk_dn_{ir.id}",
            )
        with cc3:
            v_inv = st.checkbox(
                "Invoice OK",
                value=bool(ir.invoice_ok),
                key=f"ir_d_chk_inv_{ir.id}",
            )
        pms_button_mark("draft")
        if st.button("Save checklist", type="secondary", key=f"ir_d_save_chk_{ir.id}"):
            row = session.get(InventoryReceive, ir.id)
            if row:
                row.po_document_ok = bool(v_po)
                row.delivery_note_ok = bool(v_dn)
                row.invoice_ok = bool(v_inv)
                row.updated_at = datetime.utcnow()
                session.commit()
                st.rerun()
    elif _can_edit_ir_checklist(user):
        st.caption(
            f"PO document: **{'Yes' if ir.po_document_ok else 'No'}** · "
            f"Delivery note: **{'Yes' if ir.delivery_note_ok else 'No'}** · "
            f"Invoice: **{'Yes' if ir.invoice_ok else 'No'}**"
        )
        sk = _ir_status_key(ir.status)
        if sk == "closed":
            st.caption("This receipt is **closed**; the checklist can no longer be edited.")
        elif sk == "ready_for_pickup":
            st.caption("This receipt is **ready for pickup**; the checklist can no longer be edited.")
        else:
            st.caption("The checklist can no longer be edited for this status.")
    else:
        st.caption(
            f"PO document: **{'Yes' if ir.po_document_ok else 'No'}** · "
            f"Delivery note: **{'Yes' if ir.delivery_note_ok else 'No'}** · "
            f"Invoice: **{'Yes' if ir.invoice_ok else 'No'}** "
            "(only **Purchasing** or **Master** can change these.)"
        )

    st.markdown("### Ready for pickup")
    if _can_mark_ready_for_pickup(user) and _ir_status_key(ir.status) == "open":
        if _checklist_complete_for_pickup(ir):
            st.caption("All checklist items are complete. Notify the requester that items are ready to collect.")
            if st.button("Ready to pick up", type="primary", key=f"ir_d_ready_pickup_{ir.id}"):
                row = session.get(InventoryReceive, ir.id)
                if row and _ir_status_key(row.status) == "open":
                    old_st = row.status
                    row.status = "ready_for_pickup"
                    row.pickup_ready = True
                    row.updated_at = datetime.utcnow()
                    log_ir_status_change(session, row.id, old_st, "ready_for_pickup", user.id)
                    session.commit()
                    st.rerun()
        else:
            st.caption(
                "Complete the **receiving checklist** (all three boxes) and click **Save checklist** first."
            )
    elif _ir_status_key(ir.status) == "open":
        st.caption("**Purchasing** or **Master** marks **Ready to pick up** when the requester can collect items.")
    elif _ir_status_key(ir.status) == "ready_for_pickup":
        st.success(
            "This receipt is **Ready to pick up**. The requester can accept once they have collected the items."
        )

    st.markdown("### Status log")
    hist_rows = (
        session.query(IRStatusHistory, AppUser, StudentList)
        .join(AppUser, IRStatusHistory.changed_by_id == AppUser.id)
        .join(StudentList, AppUser.student_list_id == StudentList.id)
        .filter(IRStatusHistory.ir_id == ir.id)
        .order_by(IRStatusHistory.created_at)
        .all()
    )
    if not hist_rows:
        st.caption("No status changes recorded yet.")
    else:
        log_table: List[Dict[str, str]] = []
        for h, actor, stud in hist_rows:
            actor_name = f"{stud.first_name} {stud.last_name}".strip() or actor.email
            ts = h.created_at.strftime("%Y-%m-%d %H:%M UTC") if h.created_at else "—"
            prev = h.from_status if h.from_status else "—"
            log_table.append(
                {
                    "When (UTC)": ts,
                    "By": actor_name,
                    "From": prev,
                    "To": h.to_status,
                }
            )
        st.dataframe(pd.DataFrame(log_table), hide_index=True, use_container_width=True)

    st.markdown("### Attachments")
    st.caption("Download existing files or upload a new one (max 15 MB per file).")
    atts = (
        session.query(IRAttachment)
        .filter_by(ir_id=ir.id)
        .order_by(IRAttachment.id)
        .all()
    )
    if atts:
        for att in atts:
            fp = DATA_DIR / att.stored_path
            if not fp.is_file():
                st.caption(f"Missing on disk: {att.original_filename}")
                continue
            on = att.original_filename or "file"
            st.download_button(
                label=f"Download · {on}",
                data=fp.read_bytes(),
                file_name=on,
                key=f"ir_d_dl_{att.id}",
                use_container_width=True,
            )
    else:
        st.caption("No files attached yet.")

    up = st.file_uploader("Add attachment", key=f"ir_d_ul_{ir.id}")
    if up is not None:
        body = up.getvalue()
        sig_key = f"ir_d_ul_sig_{ir.id}"
        sig = (up.name, len(body))
        if st.session_state.get(sig_key) != sig:
            if len(body) > _IR_UPLOAD_MAX_BYTES:
                st.error("File too large (max 15 MB).")
            else:
                rel = save_ir_attachment_file(DATA_DIR, ir.id, up.name or "file", body)
                session.add(
                    IRAttachment(
                        ir_id=ir.id,
                        uploaded_by_id=user.id,
                        original_filename=(up.name or "file")[:250],
                        stored_path=rel,
                    )
                )
                session.commit()
                st.session_state[sig_key] = sig
                st.rerun()
