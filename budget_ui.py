"""Budget management: assign per-team caps by class and view consumption summary."""

from __future__ import annotations

import io
import re
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session, joinedload

from models import AppUser, Class, Team
from utils import class_available_budget, net_budget_reserved_for_class, team_budget_cap_remaining


def _can_access_budget_management(user: AppUser) -> bool:
    return user.role.is_master or user.role.role_name == "head_of_purchasing"


def render_budget_management(session: Session, user: AppUser) -> None:
    if not _can_access_budget_management(user):
        st.error("Access denied.")
        st.stop()

    st.title("Budget management")
    st.caption("Set each team’s allocated budget within a class. Summary shows class-level and team-level consumption.")

    tab_assign, tab_summary = st.tabs(["Team budgets", "Summary"])

    with tab_assign:
        _tab_team_budgets(session)

    with tab_summary:
        _tab_summary(session)


def _norm_csv_header(s: str) -> str:
    return re.sub(r"\s+", "_", str(s).strip().lower())


def _team_label(t: Team) -> str:
    return f"{t.team_code} — {t.team_name}"


def _labels_in_df(df: pd.DataFrame) -> set[str]:
    if df is None or df.empty or "Team" not in df.columns:
        return set()
    out: set[str] = set()
    for x in df["Team"]:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            continue
        s = str(x).strip()
        if s:
            out.add(s)
    return out


def _parse_budget_csv(
    raw: bytes, current_class: Class
) -> Tuple[List[Dict[str, object]], List[str]]:
    """Returns (preview_rows, error_messages)."""
    errors: List[str] = []
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        return [], [f"Could not read CSV: {e}"]
    if df.empty:
        return [], ["CSV is empty."]
    norm = {_norm_csv_header(c): c for c in df.columns}
    req_full = {"class_code", "team_code", "budget_amount"}
    req_short = {"team_code", "budget_amount"}
    if not req_short.issubset(norm.keys()):
        errors.append("CSV must include columns: **team_code**, **budget_amount** (and optionally **class_code**).")
        return [], errors
    use_class_col = "class_code" in norm
    preview: List[Dict[str, object]] = []
    for i, row in df.iterrows():
        cc = str(row[norm["class_code"]]).strip() if use_class_col else current_class.class_code
        tc = str(row[norm["team_code"]]).strip()
        try:
            amt = float(row[norm["budget_amount"]])
        except (TypeError, ValueError):
            errors.append(f"Row {i + 2}: invalid budget_amount")
            continue
        if amt < 0:
            errors.append(f"Row {i + 2}: budget_amount must be >= 0")
            continue
        preview.append({"class_code": cc, "team_code": tc, "budget_amount": amt})
    return preview, errors


def _apply_budget_csv(session: Session, preview: List[Dict[str, object]]) -> List[str]:
    """Validate all rows, then apply. Returns error strings (empty if ok)."""
    errors: List[str] = []
    class_by_code = {c.class_code: c for c in session.query(Class).all()}
    resolved: List[Tuple[Team, float]] = []
    for i, r in enumerate(preview):
        cc = r["class_code"]
        tc = r["team_code"]
        amt = float(r["budget_amount"])
        cobj = class_by_code.get(cc)
        if not cobj:
            errors.append(f"Row {i + 2}: unknown class_code **{cc}**")
            continue
        team = (
            session.query(Team)
            .filter(Team.class_id == cobj.id, Team.team_code == tc, Team.is_active.is_(True))
            .first()
        )
        if not team:
            errors.append(f"Row {i + 2}: unknown team **{tc}** in class **{cc}**")
            continue
        resolved.append((team, amt))
    if errors:
        return errors
    if not resolved:
        return ["No valid rows to import."]
    for team, amt in resolved:
        team.team_budget_amount = amt
    session.commit()
    return []


def _tab_team_budgets(session: Session) -> None:
    classes = session.query(Class).order_by(Class.class_code).all()
    if not classes:
        st.warning("No classes defined. Add classes under User management → Master data.")
        return

    labels = [f"{c.class_code} — {c.class_name}" for c in classes]
    cmap = dict(zip(labels, classes))
    pick = st.selectbox("Class", labels, key="budget_mgmt_class")
    cls = cmap[pick]

    teams = (
        session.query(Team)
        .options(joinedload(Team.class_))
        .filter(Team.class_id == cls.id, Team.is_active.is_(True))
        .order_by(Team.team_code)
        .all()
    )
    if not teams:
        st.info("No active teams for this class.")
        return

    st.markdown(f"**Class budget (cap):** {float(cls.budget_amount):,.2f}")
    st.caption(
        "Edit amounts in the table or remove rows with **−** (removed teams save as **0**). "
        "Add a team with **Add to table** (each team once). Use **Import CSV** for bulk updates."
    )

    team_options = [_team_label(t) for t in teams]
    label_to_team = {_team_label(t): t for t in teams}

    widget_key = f"budget_team_editor_{cls.id}"
    init_df = pd.DataFrame(
        [{"Team": _team_label(t), "Assigned budget": float(t.team_budget_amount)} for t in teams]
    )
    if widget_key not in st.session_state:
        st.session_state[widget_key] = init_df.copy()

    df_cur = st.session_state[widget_key]
    if len(df_cur.columns) != 2 or "Team" not in df_cur.columns:
        st.session_state[widget_key] = init_df.copy()

    with st.expander("Import CSV", expanded=False):
        st.markdown(
            "Columns: **class_code**, **team_code**, **budget_amount** — or for the **selected class only**: "
            "**team_code**, **budget_amount**."
        )
        template = "class_code,team_code,budget_amount\nCS101,CS101-T1,1500.00\n"
        st.download_button(
            "Download CSV template",
            data=template,
            file_name="team_budget_template.csv",
            mime="text/csv",
            key=f"budget_csv_tpl_{cls.id}",
        )
        up = st.file_uploader("Upload CSV", type=["csv"], key=f"budget_csv_up_{cls.id}")
        if up is not None:
            raw = up.getvalue()
            preview, err = _parse_budget_csv(raw, cls)
            for e in err[:20]:
                st.warning(e)
            if len(err) > 20:
                st.caption(f"… and {len(err) - 20} more issues.")
            if preview:
                st.dataframe(pd.DataFrame(preview), hide_index=True, use_container_width=True)
                if st.button("Apply import to database", type="primary", key=f"budget_csv_apply_{cls.id}"):
                    apply_err = _apply_budget_csv(session, preview)
                    if apply_err:
                        for e in apply_err:
                            st.error(e)
                    else:
                        st.session_state[widget_key] = pd.DataFrame(
                            [
                                {"Team": _team_label(t), "Assigned budget": float(t.team_budget_amount)}
                                for t in session.query(Team)
                                .filter(Team.class_id == cls.id, Team.is_active.is_(True))
                                .order_by(Team.team_code)
                                .all()
                            ]
                        )
                        st.success(f"Imported **{len(preview)}** row(s).")
                        st.rerun()

    st.markdown("##### Team budgets")
    edited = st.data_editor(
        st.session_state[widget_key],
        column_config={
            "Team": st.column_config.TextColumn("Team", width="large"),
            "Assigned budget": st.column_config.NumberColumn(
                "Assigned budget",
                min_value=0.0,
                format="%.2f",
                step=100.0,
                width="medium",
            ),
        },
        disabled=["Team"],
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        key=widget_key,
    )

    used = _labels_in_df(edited)
    available = [o for o in team_options if o not in used]

    st.markdown("##### Add team")
    ac1, ac2, ac3 = st.columns([2.2, 1.2, 1])
    with ac1:
        if available:
            add_pick = st.selectbox(
                "Team (not already in table)",
                available,
                key=f"budget_add_pick_{cls.id}",
                label_visibility="visible",
            )
        else:
            st.caption("All teams for this class are already in the table.")
            add_pick = None
    with ac2:
        add_amt = st.number_input(
            "Assigned budget",
            min_value=0.0,
            value=0.0,
            step=100.0,
            key=f"budget_add_amt_{cls.id}",
        )
    with ac3:
        st.write("")
        st.write("")
        if st.button("Add to table", key=f"budget_add_btn_{cls.id}", disabled=not available):
            new_df = pd.concat(
                [
                    edited,
                    pd.DataFrame([{"Team": add_pick, "Assigned budget": float(add_amt)}]),
                ],
                ignore_index=True,
            )
            st.session_state[widget_key] = new_df
            st.rerun()

    sum_teams = 0.0
    for _, row in edited.iterrows():
        lab = row.get("Team")
        if lab is None or (isinstance(lab, float) and pd.isna(lab)) or str(lab).strip() == "":
            continue
        try:
            sum_teams += float(row["Assigned budget"])
        except (TypeError, ValueError):
            pass
    st.caption(f"Sum of assigned team budgets (from table): **{sum_teams:,.2f}** (may differ from class cap).")

    if st.button("Save team budgets for this class", type="primary", key="budget_save_teams"):
        amount_by_code: dict[str, float] = {}
        for _, row in edited.iterrows():
            lab = row.get("Team")
            if lab is None or (isinstance(lab, float) and pd.isna(lab)):
                continue
            lab_s = str(lab).strip()
            if not lab_s:
                continue
            t = label_to_team.get(lab_s)
            if t is None:
                st.error(f"Invalid team: {lab_s!r}. Remove the row or pick a team from Add team.")
                return
            try:
                amt = float(row["Assigned budget"])
            except (TypeError, ValueError):
                amt = 0.0
            if t.team_code in amount_by_code:
                st.error(f"Duplicate team in table: **{t.team_code}**. Remove the extra row.")
                return
            amount_by_code[t.team_code] = max(0.0, amt)

        for t in teams:
            t.team_budget_amount = float(amount_by_code.get(t.team_code, 0.0))
        session.commit()
        st.session_state[widget_key] = pd.DataFrame(
            [
                {"Team": _team_label(t), "Assigned budget": float(t.team_budget_amount)}
                for t in session.query(Team)
                .filter(Team.class_id == cls.id, Team.is_active.is_(True))
                .order_by(Team.team_code)
                .all()
            ]
        )
        st.success("Saved.")
        st.rerun()


def _tab_summary(session: Session) -> None:
    classes = session.query(Class).order_by(Class.class_code).all()
    if not classes:
        st.info("No classes.")
        return

    st.subheader("By class")
    class_rows = []
    for c in classes:
        cap = float(c.budget_amount)
        consumed = net_budget_reserved_for_class(session, c.id)
        remaining = class_available_budget(session, c.id)
        class_rows.append(
            {
                "Class": c.class_code,
                "Class name": c.class_name,
                "Total budget": cap,
                "Consumed": consumed,
                "Remaining": remaining,
            }
        )
    st.dataframe(
        pd.DataFrame(class_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Total budget": st.column_config.NumberColumn(format="%.2f"),
            "Consumed": st.column_config.NumberColumn(format="%.2f"),
            "Remaining": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    st.caption(
        "**Consumed / remaining** use class budget transactions (PR submit consumes; reject / return credits)."
    )

    st.divider()
    st.subheader("By team")
    sum_labels = [f"{c.class_code} — {c.class_name}" for c in classes]
    sum_pick = st.selectbox("Filter by class (or all)", ["All classes"] + sum_labels, key="budget_sum_class")
    team_rows = []
    q = session.query(Team).join(Class).options(joinedload(Team.class_)).filter(Team.is_active.is_(True))
    if sum_pick != "All classes":
        c = classes[sum_labels.index(sum_pick)]
        q = q.filter(Team.class_id == c.id)
    for t in q.order_by(Class.class_code, Team.team_code).all():
        cap, used, rem = team_budget_cap_remaining(session, t.id)
        team_rows.append(
            {
                "Class": t.class_.class_code,
                "Team": t.team_code,
                "Team name": t.team_name,
                "Team cap": cap,
                "Consumed (PRs)": used,
                "Remaining": rem,
            }
        )
    if not team_rows:
        st.info("No teams.")
        return
    st.dataframe(
        pd.DataFrame(team_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Team cap": st.column_config.NumberColumn(format="%.2f"),
            "Consumed (PRs)": st.column_config.NumberColumn(format="%.2f"),
            "Remaining": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    st.caption(
        "**Consumed** sums non-rejected PR totals on that team. **Remaining** = team cap minus that amount."
    )
