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

### App screenshots & branding

Login / brand artwork used in the app:

![Login branding](assets/login_brand.png)

---

## Prerequisites

Before you install anything, check the following:

| Requirement | Notes |
|-------------|--------|
| **Python** | **3.10 or newer** (3.11+ recommended). Check with `python3 --version` or `python --version`. |
| **Git** (optional) | Only needed if you clone the repository. You can also download the project as a ZIP and unpack it. |
| **Web browser** | Chrome, Firefox, Edge, or Safari — used to open the Streamlit UI. |
| **Network** | First `pip install` needs internet; running the app is local only. |

**macOS / Linux:** `python3` is usually available; you may need to install Python from [python.org](https://www.python.org/downloads/) or use Homebrew (`brew install python`).

**Windows:** Install from [python.org](https://www.python.org/downloads/) and enable **“Add python.exe to PATH”** during setup. Use **PowerShell** or **Command Prompt** for the commands below.

---

## Installation and setup

All commands below assume your terminal’s **current directory** is the project folder that contains `app.py` and `requirements.txt` (e.g. `Lab1_purchasing_app`).

### 1. Open the project folder

If you cloned with Git:

```bash
git clone <repository-url>
cd Lab1_purchasing_app
```

If you use a ZIP, unpack it, then:

```bash
cd path/to/Lab1_purchasing_app
```

### 2. Create a virtual environment

A virtual environment keeps this app’s packages separate from other Python projects.

**macOS / Linux:**

```bash
python3 -m venv .venv
```

**Windows (Command Prompt or PowerShell):**

```bash
python -m venv .venv
```

This creates a `.venv` folder in the project. It is normal for `.venv` to be listed in `.gitignore` so it is not committed.

### 3. Activate the virtual environment

You must activate the venv **every time** you open a new terminal session before running the app.

**macOS / Linux (bash/zsh):**

```bash
source .venv/bin/activate
```

**Windows — Command Prompt:**

```bash
.venv\Scripts\activate.bat
```

**Windows — PowerShell:**

```bash
.venv\Scripts\Activate.ps1
```

If PowerShell blocks scripts, run once (as Administrator if needed):  
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

When activation works, your prompt usually shows `(.venv)`.

### 4. Upgrade pip (recommended)

```bash
python -m pip install --upgrade pip
```

### 5. Install Python dependencies

Install everything required by this app from `requirements.txt`:

```bash
pip install -r requirements.txt
```

That installs at least:

- **streamlit** — web UI framework  
- **sqlalchemy** — database ORM and SQLite access  
- **pandas** — tables and CSV handling (e.g. budget import)  
- **bcrypt** — password hashing for login  

**Verify imports (optional):**

```bash
python -c "import streamlit, sqlalchemy, pandas, bcrypt; print('OK')"
```

If this prints `OK`, the environment is ready.

---

## Running the application

With the virtual environment **still activated** and your terminal in the project folder:

```bash
streamlit run app.py
```

Streamlit prints a **Local URL** (by default [http://localhost:8501](http://localhost:8501)). Open that address in your browser.

- **Stop the server:** press `Ctrl+C` in the terminal.  
- **Another app on port 8501:** run `streamlit run app.py --server.port 8502` (or any free port).

**Optional (faster reload on file changes):**

```bash
pip install watchdog
```

---

## Database and first-time seed

| Topic | Detail |
|-------|--------|
| **Where data lives** | SQLite file: `data/pms.db`. The `data/` directory is created automatically and is **gitignored** (your local DB is not pushed to Git by default). |
| **On startup** | The app creates tables if needed and runs lightweight **schema migrations** in `database.py`. |
| **Empty database** | If there are no roles yet, `seed.py` loads demo roles, users, classes, teams, suppliers, sample PRs/POs/IRs, and permissions (`seed_if_empty`). You only get this full seed **once** per new `pms.db`. |
| **After seed** | Use the [demo accounts](#demo-accounts-after-seed) below to log in. |

### Resetting to a clean demo database

To wipe local data and force a **fresh seed** on next launch:

1. Stop Streamlit (`Ctrl+C`).  
2. Delete the file `data/pms.db` (and optionally the folder `data/ir_attachments/` if you want to clear uploads).  
3. Run `streamlit run app.py` again.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| `python` / `pip` not found | Use `python3` and `pip3` on macOS/Linux, or reinstall Python with **PATH** enabled on Windows. |
| `ModuleNotFoundError: No module named 'sqlalchemy'` (or pandas, bcrypt) | Activate `.venv`, then run `pip install -r requirements.txt` again. |
| Wrong package versions | In the activated venv: `pip install --upgrade -r requirements.txt`. |
| Port already in use | `streamlit run app.py --server.port 8502` |
| Blank page or Streamlit errors | Read the stack trace in the terminal; confirm you ran `streamlit run app.py` from the folder that contains `app.py`. |
| Permission errors on `data/` | Ensure the process can create/write the `data/` directory next to `app.py`. |

---

## Demo accounts (after seed)

| Role | Email | Password |
|------|--------|----------|
| Master | master@school.com | `master123` |
| Requester | requester@school.com | `test123` |
| Approver | approver@school.com | `test123` |
| Head of purchasing | head@school.com | `test123` |
| Purchasing team | purchasing@school.com | `test123` |

---

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

---

## Remote

Repository: [TECHIN510A_Lab1_purchasing_app](https://github.com/peerayad/TECHIN510A_Lab1_purchasing_app)
