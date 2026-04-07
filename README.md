# Lab 1 — Purchasing Management System

Streamlit web app for class purchasing workflows: purchase requests (PRs), approvals, purchase orders (POs), inventory receiving, return notes, user management, and budget assignment (including CSV import).

## Work flow

Reference swimlane diagrams for the three main purchasing processes: PR lifecycle, receiving, and returns.

### 1. Purchasing process

Requester → Approver → Head of purchasing → Purchasing team. States include PR draft, submitted, approved/rejected, PO creation, and budget **consume** on submit / **return** on rejection.

![Purchasing process — PR through PO](assets/workflow-01-purchasing-process.png)

### 2. Receiving process

Purchasing team verifies PO, delivery note, and invoice; may contact the supplier if needed, then creates an **IR open**. Requester picks up the product and accepts (or enters the returning flow if not accepted).

![Receiving process — IR and pickup](assets/workflow-02-receiving-process.png)

### 3. Returning process

Requester creates a return from inventory receive, submits to the head of purchasing, drops off the product after approval, then head of purchasing inspects, completes the return, and closes the RN (**return budget** on close).

![Returning process — RN lifecycle](assets/workflow-03-returning-process.png)


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
