"""Purchase request list, draft form, detail, line-level approver workflow."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session, joinedload

from models import (
    AppUser,
    Class,
    DocumentStatus,
    Message,
    PurchaseOrder,
    PurchaseRequest,
    PurchaseRequestItem,
    PurchasingRound,
    StatusActionPermission,
    StudentList,
    Supplier,
    Team,
    TeamMembership,
)
from utils import (
    class_available_budget,
    log_pr_status_change,
    net_budget_reserved_for_class,
    next_document_number,
    recalculate_pr_budget,
    record_pr_budget_consume,
    record_pr_budget_return,
    team_budget_cap_remaining,
    validate_form,
    validate_line_items,
)

SS_SCREEN = "pr_workspace_screen"
SS_PR_ID = "pr_workspace_pr_id"
SS_PR_LIST_DF = "pr_list_selection_df"

# Column weights: Item | Description | Qty | Unit price | Sub total | Supplier | Link | Approve
_LINE_COLS = [0.38, 2.0, 0.52, 0.58, 0.62, 1.05, 1.0, 0.95]


def _pr_theme_css() -> None:
    st.markdown(
        """
<style>
.pr-page-scope section.main > div { background-color: #f5f0e6 !important; }
.pr-page-scope [data-testid="stVerticalBlock"] > div:has(.pr-form-shell) {
  background-color: #f5f0e6;
  padding: 1rem 1rem 1.5rem;
  border-radius: 10px;
}
.pr-th {
  background: #4b2e83 !important;
  color: #fff !important;
  font-weight: 600;
  font-size: 0.78rem;
  text-align: center;
  padding: 10px 6px;
  border-radius: 4px;
  font-family: system-ui, sans-serif;
}
.pr-th-left { text-align: left !important; }
div[data-testid="column"]:has(.pr-th) { background: transparent !important; }
</style>
<div class="pr-page-scope"></div>
""",
        unsafe_allow_html=True,
    )


def _line_table_header(*, show_approve: bool) -> None:
    labels = ["Item", "Description", "Qty", "Unit price", "Sub total", "Supplier", "Link"]
    if show_approve:
        labels.append("Approve")
    cols = st.columns(_LINE_COLS if show_approve else _LINE_COLS[:-1])
    for i, lab in enumerate(labels):
        extra = " pr-th-left" if i == 1 else ""
        cols[i].markdown(f'<div class="pr-th{extra}">{lab}</div>', unsafe_allow_html=True)


def load_menu_for_role(session: Session, role_id: int) -> Dict[str, Any]:
    from models import MenuVisibility

    rows = {r.menu_key: r for r in session.query(MenuVisibility).filter_by(role_id=role_id).all()}
    return rows


def get_pr_actions(session: Session, role_id: int, status_code: str) -> List[StatusActionPermission]:
    return (
        session.query(StatusActionPermission)
        .filter_by(document_type="PR", status_code=status_code, role_id=role_id, is_allowed=True)
        .all()
    )


def _restrict_class_team(user: AppUser) -> bool:
    return user.role.role_name == "requester" and not user.role.is_master


def _member_team_ids(session: Session, user_id: int) -> set[int]:
    return {m.team_id for m in session.query(TeamMembership).filter_by(user_id=user_id).all()}


def _team_eps() -> float:
    return 1e-6


def _team_budget_exceeds(session: Session, team_id: int, amount: float, ex: Optional[int]) -> Tuple[bool, float]:
    _, _, rem = team_budget_cap_remaining(session, team_id, exclude_pr_id=ex)
    return float(amount) > rem + _team_eps(), rem


def _can_approver(user: AppUser) -> bool:
    return user.role.is_master or user.role.role_name == "approver"


def _can_hop(user: AppUser) -> bool:
    return user.role.is_master or user.role.role_name == "head_of_purchasing"


def _status_badge(session: Session, doc_type: str, code: str) -> str:
    ds = session.query(DocumentStatus).filter_by(document_type=doc_type, status_code=code).first()
    name = ds.status_label if ds else code.replace("_", " ").title()
    col = (ds.status_color if ds else "gray").lower()
    colors = {"gray": ("#6c757d", "#fff"), "blue": ("#0d6efd", "#fff"), "yellow": ("#ffc107", "#212529"),
              "green": ("#198754", "#fff"), "red": ("#dc3545", "#fff")}
    bg, fg = colors.get(col, colors["gray"])
    return f'<span style="background:{bg};color:{fg};padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600;">{name}</span>'


def _go_list() -> None:
    st.session_state[SS_SCREEN] = "list"
    st.session_state.pop(SS_PR_ID, None)
    st.session_state.pop(SS_PR_LIST_DF, None)


def _go_detail(pr_id: int) -> None:
    st.session_state[SS_SCREEN] = "detail"
    st.session_state[SS_PR_ID] = pr_id


def _maybe_submitted_to_reviewed(session: Session, pr: PurchaseRequest, user: AppUser) -> bool:
    lines = session.query(PurchaseRequestItem).filter_by(pr_id=pr.id).all()
    if not lines:
        return False
    if not all(l.approver_decision in ("approved", "rejected") for l in lines):
        return False
    old = pr.status
    pr.status = "reviewed"
    pr.updated_at = datetime.utcnow()
    if all(l.approver_decision == "rejected" for l in lines):
        record_pr_budget_return(session, pr)
    log_pr_status_change(session, pr.id, old, pr.status, user.id)
    return True


def _maybe_reviewed_to_approved(session: Session, pr: PurchaseRequest, user: AppUser) -> bool:
    lines = [l for l in session.query(PurchaseRequestItem).filter_by(pr_id=pr.id).all() if l.approver_decision == "approved"]
    if not lines:
        return False
    if not all(l.hop_approved for l in lines):
        return False
    old = pr.status
    pr.status = "approved"
    pr.updated_at = datetime.utcnow()
    log_pr_status_change(session, pr.id, old, pr.status, user.id)
    return True


def render_pr_workspace(session: Session, user: AppUser, menu_rows: Dict[str, Any]) -> None:
    mv = menu_rows.get("purchase_request")
    if not mv or not mv.can_view:
        st.error("No access.")
        return
    st.session_state.setdefault(SS_SCREEN, "list")
    screen = st.session_state[SS_SCREEN]
    if screen == "list":
        _render_list(session, user, bool(mv.show_own_only))
    elif screen == "form":
        _render_form(session, user)
    else:
        _render_detail(session, user)


def _pr_list_selected_indices(event: Any) -> List[int]:
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


def _render_list(session: Session, user: AppUser, own_only: bool) -> None:
    st.subheader("Purchase requests")
    st.caption("Click a row in the table to open that purchase request.")
    q = session.query(PurchaseRequest).order_by(PurchaseRequest.id.desc())
    if own_only and not user.role.is_master:
        q = q.filter(PurchaseRequest.requester_id == user.id)
    prs = q.limit(200).all()
    if not prs:
        st.info("No purchase requests.")
    else:
        df = pd.DataFrame(
            [
                {"PR": p.pr_number, "Status": p.status, "Budget": f"{p.budget_amount:.2f}"}
                for p in prs
            ]
        )
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=SS_PR_LIST_DF,
        )
        ev = st.session_state.get(SS_PR_LIST_DF)
        for raw in _pr_list_selected_indices(ev):
            try:
                idx = int(raw)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(prs):
                _go_detail(prs[idx].id)
                st.rerun()
            break
    if user.role.role_name == "requester" or user.role.is_master:
        if st.button("New purchase request"):
            st.session_state[SS_SCREEN] = "form"
            st.session_state.pop(SS_PR_ID, None)
            st.session_state.pop("pr_line_rows", None)
            st.session_state.pop(SS_PR_LIST_DF, None)
            st.rerun()


def _default_line(sid: int) -> Dict[str, Any]:
    return {"rid": uuid.uuid4().hex[:8], "description": "", "qty": 1.0, "unit_price": 0.01, "supplier_id": sid, "link": ""}


def _render_form(session: Session, user: AppUser) -> None:
    pr_id = st.session_state.get(SS_PR_ID)
    pr: Optional[PurchaseRequest] = None
    if pr_id:
        pr = session.get(PurchaseRequest, pr_id)
        if pr and pr.status != "draft":
            _go_detail(pr.id)
            st.rerun()
            return
        if pr and pr.requester_id != user.id and not user.role.is_master:
            st.error("Cannot edit.")
            _go_list()
            st.rerun()
            return

    restrict = _restrict_class_team(user)
    mids = _member_team_ids(session, user.id) if restrict else set()
    if restrict and pr and pr.team_id not in mids:
        st.error("Not a member of this PR's team.")
        _go_list()
        st.rerun()
        return
    if restrict and not mids:
        st.error("No team memberships. Ask master to assign teams.")
        _go_list()
        st.rerun()
        return

    suppliers = session.query(Supplier).filter_by(is_active=True).order_by(Supplier.supplier_name).all()
    if not suppliers:
        st.error("No suppliers.")
        return
    sup_labels = [f"{s.supplier_code} — {s.supplier_name}" for s in suppliers]
    sup_map = {lbl: s.id for lbl, s in zip(sup_labels, suppliers)}

    if restrict:
        classes = (
            session.query(Class)
            .join(Team, Team.class_id == Class.id)
            .filter(Team.id.in_(mids), Team.is_active.is_(True))
            .distinct()
            .order_by(Class.class_code)
            .all()
        )
    else:
        classes = session.query(Class).order_by(Class.class_code).all()
    if not classes:
        st.warning("No classes.")
        return
    class_labels = [f"{c.class_code} — {c.class_name}" for c in classes]
    cmap = {lb: c.id for lb, c in zip(class_labels, classes)}

    if pr and st.session_state.get("pr_line_rows") is None:
        st.session_state["pr_line_rows"] = [
            {
                "rid": uuid.uuid4().hex[:8],
                "description": it.description,
                "qty": it.qty,
                "unit_price": it.unit_price,
                "supplier_id": it.supplier_id,
                "link": it.link or "",
            }
            for it in sorted(pr.items, key=lambda x: x.item_no)
        ] or [_default_line(suppliers[0].id)]
    elif not st.session_state.get("pr_line_rows"):
        st.session_state["pr_line_rows"] = [_default_line(suppliers[0].id)]

    line_meta: List[Dict[str, Any]] = st.session_state["pr_line_rows"]
    for row in line_meta:
        rid = row["rid"]
        st.session_state.setdefault(f"pl_{rid}_desc", row.get("description", ""))
        st.session_state.setdefault(f"pl_{rid}_qty", float(row.get("qty", 1)))
        st.session_state.setdefault(f"pl_{rid}_price", float(row.get("unit_price", 0.01)))
        st.session_state.setdefault(f"pl_{rid}_link", row.get("link", ""))

    _pr_theme_css()
    st.markdown('<div class="pr-form-shell">', unsafe_allow_html=True)
    st.markdown("### Purchase Request")

    if pr:
        try:
            ci = next(i for i, c in enumerate(classes) if c.id == pr.class_id)
        except StopIteration:
            st.error("Class not allowed.")
            st.markdown("</div>", unsafe_allow_html=True)
            return
    else:
        ci = 0

    lc, rc = st.columns(2)
    with lc:
        c_lab = st.selectbox("Class *", class_labels, index=ci, key="pr_form_class")
        cid = cmap[c_lab]

        tq = session.query(Team).filter(Team.class_id == cid, Team.is_active.is_(True))
        if restrict:
            tq = tq.filter(Team.id.in_(mids))
        teams = tq.order_by(Team.team_code).all()
        t_labels = [f"{t.team_code} — {t.team_name}" for t in teams]
        tmap = {lb: t.id for lb, t in zip(t_labels, teams)}
        if not teams:
            st.warning("No teams for this class.")
            st.markdown("</div>", unsafe_allow_html=True)
            return
        if pr:
            try:
                ti = next(i for i, t in enumerate(teams) if t.id == pr.team_id)
            except StopIteration:
                ti = 0
        else:
            ti = 0
        t_lab = st.selectbox("Team *", t_labels, index=min(ti, len(t_labels) - 1), key="pr_form_team")
        tid = tmap[t_lab]

        req_nm = f"{user.student.first_name} {user.student.last_name}".strip()
        st.text_input("Requester", value=req_nm, disabled=True, key="pr_form_req_name")

    with rc:
        rounds = session.query(PurchasingRound).filter_by(class_id=cid, is_active=True).order_by(PurchasingRound.round_name).all()
        r_labels = [r.round_name for r in rounds]
        rmap = {r.round_name: r.id for r in rounds}
        if not rounds:
            st.error("No purchasing rounds.")
            st.markdown("</div>", unsafe_allow_html=True)
            return
        if pr:
            try:
                ri = r_labels.index(next(n for n, i in rmap.items() if i == pr.purchasing_round_id))
            except (StopIteration, ValueError):
                ri = 0
        else:
            ri = 0
        r_lab = st.selectbox("Purchasing round *", r_labels, index=ri, key="pr_form_round")
        rid = rmap[r_lab]

        st.text_input("PR no.", value=pr.pr_number if pr else "—", disabled=True, key="pr_form_prno")
        st.text_input("Status", value=pr.status if pr else "draft", disabled=True, key="pr_form_stat")

    lines_data: List[Dict[str, Any]] = []
    total = 0.0
    st.markdown("#### Line items")
    _line_table_header(show_approve=False)
    w = _LINE_COLS[:-1]
    for idx, row in enumerate(line_meta, start=1):
        rid_ = row["rid"]
        c0, c1, c2, c3, c4, c5, c6 = st.columns(w)
        c0.markdown(f"<div style='text-align:center;padding-top:0.35rem'>{idx}</div>", unsafe_allow_html=True)
        with c1:
            desc = st.text_input("d", key=f"pl_{rid_}_desc", label_visibility="collapsed", placeholder="Description")
        with c2:
            qty = st.number_input("q", min_value=0.01, key=f"pl_{rid_}_qty", label_visibility="collapsed")
        with c3:
            price = st.number_input("p", min_value=0.01, key=f"pl_{rid_}_price", label_visibility="collapsed")
        stot = float(qty) * float(price)
        total += stot
        c4.markdown(f"<div style='text-align:center;padding-top:0.35rem'>{stot:.2f}</div>", unsafe_allow_html=True)
        with c5:
            sk = f"pl_{rid_}_sup"
            if sk not in st.session_state:
                sid = int(row.get("supplier_id") or suppliers[0].id)
                for lb, i in sup_map.items():
                    if i == sid:
                        st.session_state[sk] = lb
                        break
            sl = st.selectbox("s", sup_labels, key=sk, label_visibility="collapsed")
        with c6:
            link = st.text_input("l", key=f"pl_{rid_}_link", label_visibility="collapsed", placeholder="URL")
        lines_data.append(
            {"description": desc, "qty": qty, "unit_price": price, "supplier_id": sup_map[sl], "link": link}
        )

    tot_cols = st.columns(w)
    tot_cols[0].markdown("")
    tot_cols[1].markdown("")
    tot_cols[2].markdown("")
    tot_cols[3].markdown("**Total**")
    tot_cols[4].markdown(f"**{total:.2f}**")

    if st.button("+ Add line"):
        line_meta.append(_default_line(suppliers[0].id))
        st.session_state["pr_line_rows"] = line_meta
        st.rerun()

    bl, br = st.columns(2)
    with bl:
        st.text_input("Budget", value=f"{total:.2f}", disabled=True, key="pr_form_budget_preview")
    with br:
        st.markdown("")  # align with mockup: budget sits under left header column

    if tid:
        _, _, rem = team_budget_cap_remaining(session, tid, exclude_pr_id=pr.id if pr else None)
        st.info(f"Team budget remaining: **{rem:,.2f}** · This PR total **{total:,.2f}**")

    csave, csub, ccan = st.columns(3)
    with csave:
        save = st.button("Save draft", type="primary")
    with csub:
        sub = st.button("Submit")
    with ccan:
        cancel = st.button("Cancel")

    if save:
        _persist_pr(session, user, pr, cid, tid, rid, lines_data, submit=False, restrict=restrict, mids=mids)
    if sub:
        _persist_pr(session, user, pr, cid, tid, rid, lines_data, submit=True, restrict=restrict, mids=mids)
    if cancel:
        _go_list()
        st.session_state.pop("pr_line_rows", None)
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


def _persist_pr(
    session: Session,
    user: AppUser,
    pr: Optional[PurchaseRequest],
    cid: int,
    tid: int,
    rid: int,
    lines_data: List[Dict[str, Any]],
    submit: bool,
    restrict: bool,
    mids: set[int],
) -> None:
    ok, msgs = validate_form(session, "purchase_requests", {"class_id": cid, "team_id": tid, "purchasing_round_id": rid})
    lok, lmsgs = validate_line_items(session, lines_data)
    for m in msgs + lmsgs:
        st.error(m)
    if msgs or lmsgs:
        return
    created = False
    if pr is None:
        pr = PurchaseRequest(
            pr_number=next_document_number(session, "PR"),
            requester_id=user.id,
            class_id=cid,
            team_id=tid,
            purchasing_round_id=rid,
            budget_amount=0.0,
            status="draft",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(pr)
        session.flush()
        log_pr_status_change(session, pr.id, None, "draft", user.id)
        st.session_state[SS_PR_ID] = pr.id
        created = True
    else:
        pr.class_id = cid
        pr.team_id = tid
        pr.purchasing_round_id = rid
        pr.updated_at = datetime.utcnow()
    session.query(PurchaseRequestItem).filter_by(pr_id=pr.id).delete(synchronize_session=False)
    for j, row in enumerate(lines_data, start=1):
        stot = float(row["qty"]) * float(row["unit_price"])
        session.add(
            PurchaseRequestItem(
                pr_id=pr.id,
                item_no=j,
                description=row["description"] or " ",
                qty=float(row["qty"]),
                unit_price=float(row["unit_price"]),
                sub_total=stot,
                supplier_id=int(row["supplier_id"]),
                link=row.get("link") or None,
                created_at=datetime.utcnow(),
                approver_decision=None,
                hop_approved=False,
            )
        )
    recalculate_pr_budget(session, pr.id)
    if restrict and tid not in mids:
        session.rollback()
        if created:
            st.session_state.pop(SS_PR_ID, None)
        st.error("Invalid team.")
        return
    if restrict:
        bad, rem = _team_budget_exceeds(session, tid, pr.budget_amount, pr.id)
        if bad:
            session.rollback()
            if created:
                st.session_state.pop(SS_PR_ID, None)
            st.error(f"Exceeds team budget. Remaining {rem:,.2f}.")
            return
    if submit:
        avail = class_available_budget(session, pr.class_id)
        if avail < float(pr.budget_amount):
            session.rollback()
            if created:
                st.session_state.pop(SS_PR_ID, None)
            st.error("Insufficient class budget.")
            return
        old = pr.status
        pr.status = "submitted"
        pr.updated_at = datetime.utcnow()
        record_pr_budget_consume(session, pr)
        log_pr_status_change(session, pr.id, old, "submitted", user.id)
    session.commit()
    st.success("Submitted." if submit else "Saved.")
    if submit:
        st.session_state[SS_SCREEN] = "detail"
    st.rerun()


def _apply_workflow(session: Session, user: AppUser, pr: PurchaseRequest, sap: StatusActionPermission) -> None:
    if sap.action_key == "delete":
        session.delete(pr)
        session.commit()
        _go_list()
        st.rerun()
        return
    if sap.action_key == "create_po":
        session.add(
            PurchaseOrder(
                po_number=next_document_number(session, "PO"),
                pr_id=pr.id,
                purchasing_team_id=user.id,
                status="open",
                created_at=datetime.utcnow(),
            )
        )
        session.commit()
        st.rerun()
        return
    old = pr.status
    if sap.action_key == "reject" or sap.next_status == "rejected":
        pr.status = "rejected"
        record_pr_budget_return(session, pr)
        for li in pr.items:
            li.approver_decision = None
            li.hop_approved = False
    elif sap.next_status:
        pr.status = sap.next_status
    pr.updated_at = datetime.utcnow()
    log_pr_status_change(session, pr.id, old, pr.status, user.id)
    session.commit()
    st.rerun()


def _render_detail(session: Session, user: AppUser) -> None:
    pr_id = st.session_state.get(SS_PR_ID)
    if not pr_id:
        _go_list()
        st.rerun()
        return
    pr = (
        session.query(PurchaseRequest)
        .options(
            joinedload(PurchaseRequest.items).joinedload(PurchaseRequestItem.supplier),
            joinedload(PurchaseRequest.class_),
            joinedload(PurchaseRequest.team),
            joinedload(PurchaseRequest.purchasing_round),
            joinedload(PurchaseRequest.requester).joinedload(AppUser.student),
        )
        .filter_by(id=pr_id)
        .first()
    )
    if not pr:
        st.error("Not found.")
        _go_list()
        st.rerun()
        return

    if st.button("← Back"):
        _go_list()
        st.rerun()

    _pr_theme_css()
    st.markdown('<div class="pr-form-shell">', unsafe_allow_html=True)
    st.markdown(f"## Purchase Request `{pr.pr_number}`")
    st.markdown(_status_badge(session, "PR", pr.status), unsafe_allow_html=True)

    for sap in get_pr_actions(session, user.role_id, pr.status):
        if sap.action_key in ("submit", "edit"):
            continue
        if st.button(sap.button_label, key=f"sap_{sap.id}"):
            _apply_workflow(session, user, pr, sap)

    if pr.status == "draft" and (pr.requester_id == user.id or user.role.is_master):
        if st.button("Edit draft", type="primary"):
            st.session_state[SS_SCREEN] = "form"
            st.session_state["pr_line_rows"] = None
            st.rerun()

    lc, rc = st.columns(2)
    with lc:
        st.text_input("Class", value=pr.class_.class_code if pr.class_ else "", disabled=True, key=f"d_cl_{pr.id}")
        st.text_input("Team", value=pr.team.team_code if pr.team else "", disabled=True, key=f"d_tm_{pr.id}")
        rq = pr.requester.student if pr.requester else None
        st.text_input(
            "Requester",
            value=f"{rq.first_name} {rq.last_name}" if rq else "",
            disabled=True,
            key=f"d_rq_{pr.id}",
        )
        st.text_input("Budget", value=f"{pr.budget_amount:.2f}", disabled=True, key=f"d_bd_{pr.id}")
    with rc:
        st.text_input(
            "Purchasing round",
            value=pr.purchasing_round.round_name if pr.purchasing_round else "",
            disabled=True,
            key=f"d_rn_{pr.id}",
        )
        st.text_input("PR no.", value=pr.pr_number, disabled=True, key=f"d_no_{pr.id}")
        st.text_input("Status", value=pr.status, disabled=True, key=f"d_st_{pr.id}")

    cls = session.get(Class, pr.class_id)
    if cls:
        cons = net_budget_reserved_for_class(session, pr.class_id)
        st.caption(f"Class budget: {cls.budget_amount:.2f} · consumed (net) {cons:.2f}")

    items = sorted(pr.items, key=lambda x: x.item_no)
    show_apr_col = pr.status in ("submitted", "reviewed", "approved")

    st.markdown("#### Line items")
    if pr.status == "submitted" and _can_approver(user):
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Approve all lines", key=f"pa_all_{pr.id}"):
                for it in items:
                    it.approver_decision = "approved"
                pr.updated_at = datetime.utcnow()
                if _maybe_submitted_to_reviewed(session, pr, user):
                    session.commit()
                    st.rerun()
                session.commit()
                st.rerun()
        with b2:
            if st.button("Reject all lines", key=f"pr_all_{pr.id}"):
                for it in items:
                    it.approver_decision = "rejected"
                pr.updated_at = datetime.utcnow()
                if _maybe_submitted_to_reviewed(session, pr, user):
                    session.commit()
                    st.rerun()
                session.commit()
                st.rerun()

    _line_table_header(show_approve=show_apr_col)
    w = _LINE_COLS if show_apr_col else _LINE_COLS[:-1]

    for it in items:
        cols = st.columns(w)
        cols[0].markdown(f"<div style='text-align:center'>{it.item_no}</div>", unsafe_allow_html=True)
        cols[1].markdown(it.description)
        cols[2].markdown(f"<div style='text-align:center'>{it.qty:g}</div>", unsafe_allow_html=True)
        cols[3].markdown(f"<div style='text-align:center'>{it.unit_price:.2f}</div>", unsafe_allow_html=True)
        cols[4].markdown(f"<div style='text-align:center'>{it.sub_total:.2f}</div>", unsafe_allow_html=True)
        cols[5].markdown(it.supplier.supplier_name if it.supplier else "—")
        cols[6].markdown(it.link or "—")
        ad = it.approver_decision
        hd = it.hop_approved
        if show_apr_col:
            ac = cols[7]
            if pr.status == "submitted" and _can_approver(user):
                if ad is None:
                    y1, y2 = ac.columns(2)
                    if y1.button("Y", key=f"py_{pr.id}_{it.id}", use_container_width=True):
                        it.approver_decision = "approved"
                        if _maybe_submitted_to_reviewed(session, pr, user):
                            session.commit()
                            st.rerun()
                        session.commit()
                        st.rerun()
                    if y2.button("N", key=f"pn_{pr.id}_{it.id}", use_container_width=True):
                        it.approver_decision = "rejected"
                        if _maybe_submitted_to_reviewed(session, pr, user):
                            session.commit()
                            st.rerun()
                        session.commit()
                        st.rerun()
                else:
                    ac.caption("✓ Yes" if ad == "approved" else "✗ No")
            elif pr.status == "reviewed" and _can_hop(user) and ad == "approved":
                if not hd:
                    if ac.button("HoP ✓", key=f"hy_{pr.id}_{it.id}", use_container_width=True):
                        it.hop_approved = True
                        pr.updated_at = datetime.utcnow()
                        if _maybe_reviewed_to_approved(session, pr, user):
                            session.commit()
                            st.rerun()
                        session.commit()
                        st.rerun()
                else:
                    ac.caption("HoP OK")
            elif pr.status == "reviewed" and ad == "rejected":
                ac.caption("—")
            else:
                ac.caption("✓" if ad == "approved" else ("✗" if ad == "rejected" else "—"))

    tot_cols = st.columns(w)
    tot_cols[0].markdown("")
    tot_cols[1].markdown("")
    tot_cols[2].markdown("")
    tot_cols[3].markdown("**Total**")
    tot_cols[4].markdown(f"**{pr.budget_amount:.2f}**")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### Messages")
    msg_rows = (
        session.query(Message, AppUser, StudentList)
        .join(AppUser, Message.sender_id == AppUser.id)
        .join(StudentList, AppUser.student_list_id == StudentList.id)
        .filter(Message.reference_id == pr.id, Message.reference_type == "PR")
        .order_by(Message.timestamp)
        .all()
    )
    if not msg_rows:
        st.caption("No messages yet.")
    for m, sender, stud in msg_rows:
        name = f"{stud.first_name} {stud.last_name}".strip() or sender.email
        ts_label = m.timestamp.strftime("%Y-%m-%d %H:%M UTC") if m.timestamp else "—"
        st.markdown(f"**{name}** · `{ts_label}`")
        st.write(m.message)
    nm = st.text_area("Add message", key=f"m_{pr.id}")
    if st.button("Send", key=f"ms_{pr.id}"):
        if nm.strip():
            session.add(
                Message(
                    reference_id=pr.id,
                    reference_type="PR",
                    sender_id=user.id,
                    message=nm.strip(),
                    timestamp=datetime.utcnow(),
                )
            )
            session.commit()
            st.rerun()
