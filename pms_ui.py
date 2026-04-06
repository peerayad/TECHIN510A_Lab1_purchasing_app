"""Shared Streamlit styling: buttons, form fields (logged-in app)."""

from __future__ import annotations

from typing import Any, Literal, Optional

import streamlit as st

BtnMark = Literal["draft", "danger", "orange"]

# Warm cream page fill (login + all logged-in pages)
PMS_CREAM_BG = "#f5f0e6"


def inject_pms_page_background() -> None:
    """Cream background for the full app viewport and main content wrappers."""
    st.markdown(
        f"""
<style>
html, body {{
  background-color: {PMS_CREAM_BG} !important;
}}
.stApp {{
  background-color: {PMS_CREAM_BG} !important;
}}
[data-testid="stAppViewContainer"] {{
  background-color: {PMS_CREAM_BG} !important;
}}
[data-testid="stAppViewContainer"] > .main,
[data-testid="stAppViewContainer"] > .main > div,
[data-testid="stAppViewContainer"] .stMainBlockContainer {{
  background-color: {PMS_CREAM_BG} !important;
}}
section.main,
section.main > div,
.block-container {{
  background-color: {PMS_CREAM_BG} !important;
}}
/* Streamlit inner scroll / decoration strip */
[data-testid="stHeader"] {{
  background-color: {PMS_CREAM_BG} !important;
}}
footer[data-testid="stFooter"] {{
  background-color: {PMS_CREAM_BG} !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )


def inject_pms_button_styles() -> None:
    """Call once per logged-in page (e.g. from app shell). Login form styling stays separate."""
    st.markdown(
        """
<style>
/* Zero-height slot so marker rows don’t push buttons out of alignment */
.pms-btn-mark-wrap {
  height: 0 !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  line-height: 0 !important;
  overflow: hidden !important;
  font-size: 0 !important;
  border: none !important;
}

/* Green — primary (submit, complete, accept, approve, create PO, etc.) */
[data-testid="stAppViewContainer"] button[kind="primary"],
[data-testid="stAppViewContainer"] button[data-testid="baseButton-primary"],
section.main button[kind="primary"],
section.main button[data-testid="baseButton-primary"] {
  background-color: #16a34a !important;
  border: 1px solid #15803d !important;
  color: #ffffff !important;
}
[data-testid="stAppViewContainer"] button[kind="primary"]:hover,
[data-testid="stAppViewContainer"] button[data-testid="baseButton-primary"]:hover,
section.main button[kind="primary"]:hover,
section.main button[data-testid="baseButton-primary"]:hover {
  background-color: #15803d !important;
  border-color: #166534 !important;
  color: #ffffff !important;
}

/* Blue — save draft / persist (marker immediately before secondary button only) */
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-draft)
  + div[data-testid="stElementContainer"] button[kind="secondary"],
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-draft)
  + div[data-testid="stElementContainer"] button[data-testid="baseButton-secondary"],
section.main div.element-container:has(span.pms-btn-mark-draft)
  + div.element-container button[kind="secondary"],
section.main div.element-container:has(span.pms-btn-mark-draft)
  + div.element-container button[data-testid="baseButton-secondary"] {
  background-color: #2563eb !important;
  border: 1px solid #1d4ed8 !important;
  color: #ffffff !important;
}
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-draft)
  + div[data-testid="stElementContainer"] button[kind="secondary"]:hover,
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-draft)
  + div[data-testid="stElementContainer"] button[data-testid="baseButton-secondary"]:hover,
section.main div.element-container:has(span.pms-btn-mark-draft)
  + div.element-container button[kind="secondary"]:hover,
section.main div.element-container:has(span.pms-btn-mark-draft)
  + div.element-container button[data-testid="baseButton-secondary"]:hover {
  background-color: #1d4ed8 !important;
  border-color: #1e40af !important;
}

/* Orange — e.g. IR “Return” (secondary only) */
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-orange)
  + div[data-testid="stElementContainer"] button[kind="secondary"],
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-orange)
  + div[data-testid="stElementContainer"] button[data-testid="baseButton-secondary"],
section.main div.element-container:has(span.pms-btn-mark-orange)
  + div.element-container button[kind="secondary"],
section.main div.element-container:has(span.pms-btn-mark-orange)
  + div.element-container button[data-testid="baseButton-secondary"] {
  background-color: #ea580c !important;
  border: 1px solid #c2410c !important;
  color: #ffffff !important;
}
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-orange)
  + div[data-testid="stElementContainer"] button[kind="secondary"]:hover,
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-orange)
  + div[data-testid="stElementContainer"] button[data-testid="baseButton-secondary"]:hover,
section.main div.element-container:has(span.pms-btn-mark-orange)
  + div.element-container button[kind="secondary"]:hover,
section.main div.element-container:has(span.pms-btn-mark-orange)
  + div.element-container button[data-testid="baseButton-secondary"]:hover {
  background-color: #c2410c !important;
  border-color: #9a3412 !important;
}

/* Red — cancel / reject / delete: secondary buttons only (never restyle primary “Completed” etc.) */
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-danger)
  + div[data-testid="stElementContainer"] button[kind="secondary"],
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-danger)
  + div[data-testid="stElementContainer"] button[data-testid="baseButton-secondary"],
section.main div.element-container:has(span.pms-btn-mark-danger)
  + div.element-container button[kind="secondary"],
section.main div.element-container:has(span.pms-btn-mark-danger)
  + div.element-container button[data-testid="baseButton-secondary"] {
  background-color: #dc2626 !important;
  border: 1px solid #b91c1c !important;
  color: #ffffff !important;
}
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-danger)
  + div[data-testid="stElementContainer"] button[kind="secondary"]:hover,
section.main div[data-testid="stElementContainer"]:has(span.pms-btn-mark-danger)
  + div[data-testid="stElementContainer"] button[data-testid="baseButton-secondary"]:hover {
  background-color: #b91c1c !important;
  border-color: #991b1b !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def inject_pms_input_field_styles() -> None:
    """Editable inputs: white. Disabled / DB read-only fields: gray. Login screen is unchanged (shell only)."""
    st.markdown(
        """
<style>
/* ---- Editable fields (white) ---- */
[data-testid="stAppViewContainer"] [data-testid="stTextInput"] input:not([disabled]),
[data-testid="stAppViewContainer"] [data-testid="stNumberInput"] input:not([disabled]),
[data-testid="stAppViewContainer"] [data-testid="stTextArea"] textarea:not([disabled]),
[data-testid="stAppViewContainer"] [data-testid="stDateInput"] input:not([disabled]),
[data-testid="stAppViewContainer"] [data-testid="stTimeInput"] input:not([disabled]) {
  background-color: #ffffff !important;
  color: #1a1a1a !important;
  -webkit-text-fill-color: #1a1a1a !important;
}

/* ---- View-only / disabled (gray) ---- */
[data-testid="stAppViewContainer"] [data-testid="stTextInput"] input[disabled],
[data-testid="stAppViewContainer"] [data-testid="stNumberInput"] input[disabled],
[data-testid="stAppViewContainer"] [data-testid="stTextArea"] textarea[disabled],
[data-testid="stAppViewContainer"] [data-testid="stDateInput"] input[disabled],
[data-testid="stAppViewContainer"] [data-testid="stTimeInput"] input[disabled] {
  background-color: #e5e7eb !important;
  color: #4b5563 !important;
  border-color: #d1d5db !important;
  -webkit-text-fill-color: #4b5563 !important;
  opacity: 1 !important;
  cursor: default !important;
}

/* Select / multiselect: enabled ≈ white control surface */
[data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [data-baseweb="select"] > div:first-child:not([aria-disabled="true"]),
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] [data-baseweb="select"] > div:first-child:not([aria-disabled="true"]) {
  background-color: #ffffff !important;
  color: #1a1a1a !important;
}

[data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [data-baseweb="select"] > div:first-child[aria-disabled="true"],
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] [data-baseweb="select"] > div:first-child[aria-disabled="true"] {
  background-color: #e5e7eb !important;
  color: #4b5563 !important;
  border-color: #d1d5db !important;
  opacity: 1 !important;
  cursor: default !important;
}

/* Combobox role (some Streamlit versions) */
[data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [role="combobox"]:not([aria-disabled="true"]),
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] [role="combobox"]:not([aria-disabled="true"]) {
  background-color: #ffffff !important;
}
[data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [role="combobox"][aria-disabled="true"],
[data-testid="stAppViewContainer"] [data-testid="stMultiSelect"] [role="combobox"][aria-disabled="true"] {
  background-color: #e5e7eb !important;
  color: #4b5563 !important;
  opacity: 1 !important;
}

/* Number input stepper buttons stay readable */
[data-testid="stAppViewContainer"] [data-testid="stNumberInput"] button {
  opacity: 1 !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def pms_button_mark(mark: Optional[BtnMark], *, container: Optional[Any] = None) -> None:
    """Slot before ``st.button``: ``draft`` / ``danger`` / ``orange`` for colors; ``None`` for an empty slot (keeps rows aligned).

    Pass ``container=col`` when emitting inside ``with col:`` / ``col.button`` so the slot stays in that column.
    """
    if mark is None:
        inner = '<span class="pms-btn-mark-empty"></span>'
    else:
        inner = f'<span class="pms-btn-mark-{mark}"></span>'
    dg = container if container is not None else st
    dg.markdown(
        f'<div class="pms-btn-mark-wrap" aria-hidden="true">{inner}</div>',
        unsafe_allow_html=True,
    )
