# Lab 1 — Purchasing Management System

Streamlit web app for class purchasing workflows: purchase requests (PRs), approvals, purchase orders (POs), inventory receiving, return notes, user management, and budget assignment (including CSV import).

## Requirements

- Python 3.10+ (3.11+ recommended)

## Setup

```bash
cd Lab1_purchasing_app
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

If you see import errors for **SQLAlchemy**, **pandas**, or **bcrypt**, install them explicitly:

```bash
pip install sqlalchemy pandas bcrypt
```

## Run

```bash
streamlit run app.py
```

The app opens in your browser (default [http://localhost:8501](http://localhost:8501)).

## Database

SQLite is stored under `data/pms.db` (the `data/` folder is gitignored). Tables are created and migrated on startup.

On **first run** with an empty database, sample roles, users, classes, teams, suppliers, and demo PR/PO data are loaded automatically (`seed_if_empty`).

## Demo accounts (after seed)

| Role | Email | Password |
|------|--------|----------|
| Master | master@school.com | `master123` |
| Requester | requester@school.com | `test123` |
| Approver | approver@school.com | `test123` |
| Head of purchasing | head@school.com | `test123` |
| Purchasing team | purchasing@school.com | `test123` |

## Project layout

| Path | Purpose |
|------|---------|
| `app.py` | Streamlit entrypoint, routing, login |
| `models.py` | SQLAlchemy models |
| `database.py` | SQLite engine, sessions, migrations |
| `seed.py` | One-time seed when DB is empty |
| `auth.py` | Login, password hashing |
| `*_ui.py` | Feature screens (PR, PO, IR, RN, budget, etc.) |
| `user_management.py` | Master data and users |
| `utils.py` | Budget and validation helpers |

## Remote

Repository: [TECHIN510A_Lab1_purchasing_app](https://github.com/peerayad/TECHIN510A_Lab1_purchasing_app)
