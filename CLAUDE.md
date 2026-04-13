# CLAUDE.md — Purchasing Management System (TECHIN 510, UW GIX)

Context for AI assistants and developers working on this **Lab 1** Streamlit application for **TECHIN 510** at the **University of Washington Global Innovation Exchange (GIX)**.

## What this app is

A **Purchasing Management System (PMS)** web UI for class-aligned procurement workflows:

- **Purchase requests (PRs)** — draft, submit, approvals, budget checks  
- **Purchase orders (POs)** — created from approved PR lines  
- **Inventory receipts (IRs)** — receiving / pickup / acceptance  
- **Return notes (RNs)** — returns tied to receipts  
- **Budgets** — class/team caps, CSV import (master / head of purchasing)  
- **User management** — master-only students, roles, permissions  

Workflow diagrams and screenshots live in **`README.md`** and **`assets/`**.

## Who uses it

**GIX students and staff** in role-based personas (see seed / `README.md` demo accounts):

| Persona | Typical use |
|---------|-------------|
| **Requester** | Creates PRs; often sees **own** PRs only (`show_own_only`) |
| **Approver** | Line / stage approvals on submitted PRs |
| **Head of purchasing** | Final PR approval path; budget menu visibility |
| **Purchasing team** | POs, inventory receiving |
| **Master** | Full access, user management, clearing demo procurement data |

Auth is **email + password** with **bcrypt** hashing (`auth.py`). Permissions combine **roles**, **`MenuVisibility`**, and **`Permission`** rows (`models.py`, seed).

## Tech stack

| Layer | Choice |
|-------|--------|
| Language | **Python 3.11+** |
| UI | **Streamlit** (`app.py` + `*_ui.py`) |
| Database | **SQLite** file under **`data/`** (gitignored) |
| ORM | **SQLAlchemy** 2.x (`models.py`, `database.py`) |
| Charts | **Plotly** (`dashboard.py`; use `st.plotly_chart`) |
| Tables / CSV | **pandas** (`budget_ui`, PR/PO/IR/RN tables) |
| Passwords | **bcrypt** (`auth.py`) |

Dependencies are listed in **`requirements.txt`**.

## Project structure

| Path | Role |
|------|------|
| `app.py` | Entrypoint: page config, login, top nav, routing to workspaces |
| `dashboard.py` | Metrics, Plotly charts, cached chart data prep |
| `models.py` | SQLAlchemy models (PR, PO, IR, RN, users, budget, menus, …) |
| `database.py` | Engine, `get_session()`, SQLite migrations |
| `seed.py` | One-time seed when DB has no roles |
| `auth.py` | Login, session user, hashing |
| `utils.py` | Document numbers, budget consume/return, validation helpers |
| `pr_ui.py` / `po_ui.py` / `ir_ui.py` / `rn_ui.py` | Feature workspaces |
| `budget_ui.py` | Budget management UI |
| `user_management.py` | Master user & master data |
| `pms_ui.py` | Shared Streamlit CSS (buttons, layout) |
| `data/` | **`pms.db`** and **`ir_attachments/`** at runtime (not in Git) |
| `.cursorrules` | Project coding / Streamlit / Plotly conventions for Cursor |

## Development commands

From the repository root (folder containing `app.py`):

```bash
# Create and use a virtual environment (macOS/Linux example)
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt

# Optional: confirm imports
python -c "import streamlit, sqlalchemy, pandas, bcrypt, plotly; print('OK')"

# Run the app
streamlit run app.py
# Default: http://localhost:8501
# Alt port: streamlit run app.py --server.port 8502
```

**Reset demo DB:** stop the app, delete `data/pms.db` (and optionally `data/ir_attachments/`), start again to re-run **`seed_if_empty`**.

## Coding standards

- **Type hints** on public functions; prefer modern union syntax (`X | None`) with `from __future__ import annotations` where helpful.  
- **Google-style docstrings** for non-trivial modules and functions.  
- **Clear names** (`pr_q`, `rows_snapshot`, `net_budget_reserved`); avoid cryptic abbreviations.  
- **Small functions** — aim **under ~30 lines**; extract helpers when a screen grows.  
- **Streamlit** — use **`st.cache_data`** for pure, repeatable data prep; pass **hashable** arguments only (normalize SQLAlchemy rows to plain `tuple[str, int]` snapshots before caching). Use **`st.error`** / **`st.warning`** / **`st.info`** for user-visible outcomes.  
- **Plotly** — titles, axis labels, and sensible hovers; follow **`.cursorrules`** for the standard PR status palette when applicable.  
- **Security** — never commit secrets, `.env`, or `data/pms.db`; enforce menu/role checks before sensitive actions.

## Important notes

1. **Single-process SQLite** — one writer at a time; fine for local lab demos; not a production multi-user server layout.  
2. **Migrations** — additive SQLite changes live in **`database.py`** (`migrate_sqlite_schema`); new columns must remain backward-compatible for existing `pms.db` files.  
3. **Budget semantics** — PR submit/consume and reject/return paths touch **`BudgetTransaction`** and helpers in **`utils.py`**; team caps appear in **`pr_ui.py`**.  
4. **Streamlit reruns** — the whole script reruns on interaction; use **`st.session_state`** for navigation and wizard state; avoid storing **`Session`** inside session state.  
5. **README** — authoritative setup, troubleshooting, demo accounts, and **Repositories** section for remotes used in class.  
6. **Course** — behavior and copy should stay aligned with **TECHIN 510** lab specs and any interview / stakeholder notes (e.g. Dorothy / student purchasing) referenced in deliverables.

When unsure, read **`README.md`**, **`.cursorrules`**, and the relevant `*_ui.py` before changing workflow or permissions.
