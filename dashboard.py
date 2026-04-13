"""Home dashboard and menu visibility helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from models import AppUser, MenuVisibility, PurchaseOrder, PurchaseRequest, ReturnNote

# Primary statuses for the chart (always shown, in this order, with 0 if none).
_PR_CHART_PRIMARY = ("draft", "submitted", "approved", "rejected")

# Exact bar colors for draft, submitted, approved, rejected (other statuses use fallback).
_PR_STATUS_COLORS: Dict[str, str] = {
    "draft": "#1f77b4",
    "submitted": "#ff7f0e",
    "approved": "#2ca02c",
    "rejected": "#d62728",
}
_PR_EXTRA_STATUS_COLOR = "#7f7f7f"


def _pr_status_rows_snapshot(rows: List[Tuple[object, object]]) -> tuple[tuple[str, int], ...]:
    """Plain Python pairs so Streamlit cache hashing works (SQLAlchemy Row / numpy int break hash)."""
    return tuple(
        (str(r[0]), int(r[1]))
        for r in sorted(rows, key=lambda r: (str(r[0]), int(r[1])))
    )


@st.cache_data(show_spinner=False)
def _prepare_pr_status_chart_data(status_count_pairs: tuple[tuple[str, int], ...]) -> dict[str, list]:
    """
    Build ordered labels, counts, and per-bar colors for the PR-by-status chart.
    Cached on a hashable snapshot of (status, count) pairs from the DB.

    Args:
        status_count_pairs: A tuple of (status, count) tuples retrieved from the database.

    Returns:
        Dictionary containing:
            - x_labels: List of formatted status labels for the x-axis.
            - counts: List of counts corresponding to each status.
            - colors: List of color codes for each bar based on status.
    """
    # Convert the input pairs to a dictionary for easy lookup.
    status_to_count: dict[str, int] = dict(status_count_pairs)
    
    # Initialize the ordered list with primary statuses,
    # ensuring a stable order and showing 0 if a primary status is missing.
    ordered_status_counts: List[Tuple[str, int]] = [
        (primary_status, int(status_to_count.get(primary_status, 0))) 
        for primary_status in _PR_CHART_PRIMARY
    ]

    # Track which statuses we've already included to avoid duplicates.
    seen_statuses = set(_PR_CHART_PRIMARY)
    
    # Append any extra (non-primary) statuses in sorted order.
    for status, count in sorted(status_count_pairs, key=lambda pair: pair[0]):
        if status not in seen_statuses:
            ordered_status_counts.append((status, int(count)))
            seen_statuses.add(status)
    
    # Split into separate lists for status labels and counts.
    status_list = [status for status, _ in ordered_status_counts]
    count_list = [count for _, count in ordered_status_counts]
    
    # Format labels: Replace underscores with spaces and capitalize words.
    x_axis_labels = [status.replace("_", " ").title() for status in status_list]
    
    # Assign bar colors: Use defined color for status if set, otherwise use fallback color.
    color_list = [_PR_STATUS_COLORS.get(status, _PR_EXTRA_STATUS_COLOR) for status in status_list]

    return {
        "x_labels": x_axis_labels,
        "counts": count_list,
        "colors": color_list,
    }


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


def _visible_pr_query(session: Session, user: AppUser, pr_mv: MenuView) -> Query:
    q = session.query(PurchaseRequest)
    if pr_mv.show_own_only and not user.role.is_master:
        q = q.filter(PurchaseRequest.requester_id == user.id)
    return q


def _status_counts_rows(q: Query, status_col, id_col) -> List[Tuple[str, int]]:
    rows = (
        q.with_entities(status_col, func.count(id_col)).group_by(status_col).all()
    )
    return sorted(rows, key=lambda r: r[1], reverse=True)


def _pr_status_plotly_figure(prepared: dict[str, list]) -> go.Figure:
    """Plotly bar chart from cached prepared data (not st.bar_chart)."""
    x_labels = prepared["x_labels"]
    counts = prepared["counts"]
    colors = prepared["colors"]
    fig = go.Figure(
        data=[
            go.Bar(
                x=x_labels,
                y=counts,
                marker_color=colors,
                marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Count: %{y:d}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title={"text": "Purchase Requests by Status", "x": 0.5, "xanchor": "center"},
        xaxis_title="Status",
        yaxis_title="Number of purchase requests",
        showlegend=False,
        bargap=0.25,
        yaxis=dict(rangemode="tozero", tickformat="d"),
        margin=dict(t=50, l=48, r=24, b=48),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(245,240,230,0.35)",
    )
    fig.update_xaxes(tickangle=-25)
    return fig


def render_dashboard(session: Session, user: AppUser) -> None:
    st.title("Dashboard")
    st.caption("Overview of active purchase requests and order pipeline")
    st.caption(f"Signed in as **{user.email}** ({user.role.role_name.replace('_', ' ')})")

    mv = load_menu_visibility(session, user.role.id)
    by_key = {k: v for k, v in mv.items() if v.can_view}

    pr_q: Query | None = None
    n_pr = 0
    if "purchase_request" in by_key:
        pr_q = _visible_pr_query(session, user, by_key["purchase_request"])
        n_pr = pr_q.count()
        st.metric("Purchase requests (visible)", n_pr)

    if "inventory_return" in by_key:
        q = session.query(ReturnNote)
        n_rn = q.filter(ReturnNote.status.in_(("draft", "submitted", "approved"))).count()
        st.metric("Return notes (active pipeline)", n_rn)

    show_pr_chart = pr_q is not None
    show_po_chart = "purchase_order" in by_key
    if show_pr_chart or show_po_chart:
        st.subheader("Charts")
        chart_cols = st.columns(2 if show_pr_chart and show_po_chart else 1)
        idx = 0

        if show_pr_chart:
            with chart_cols[idx]:
                if n_pr == 0:
                    st.info("No purchase requests yet.")
                else:
                    rows = _status_counts_rows(pr_q, PurchaseRequest.status, PurchaseRequest.id)
                    prepared = _prepare_pr_status_chart_data(_pr_status_rows_snapshot(rows))
                    fig = _pr_status_plotly_figure(prepared)
                    st.plotly_chart(fig, use_container_width=True)
            idx += 1

        if show_po_chart:
            with chart_cols[idx] if show_pr_chart and show_po_chart else chart_cols[0]:
                st.caption("Purchase orders by status")
                po_q = session.query(PurchaseOrder)
                rows = _status_counts_rows(po_q, PurchaseOrder.status, PurchaseOrder.id)
                if rows:
                    df = pd.DataFrame(rows, columns=["status", "count"]).set_index("status")
                    df.index = df.index.astype(str).str.replace("_", " ").str.title()
                    st.bar_chart(df.rename(columns={"count": "POs"}))
                else:
                    st.info("No purchase orders yet.")

    if user.role.is_master:
        st.divider()
        if st.button("Open user management", type="primary", key="dash_um"):
            st.session_state["pms_navigate_to_page"] = "user_management"
            st.rerun()
