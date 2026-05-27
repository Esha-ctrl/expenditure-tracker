# Implementation Plan — Step 1: Database Setup (Spendly)

## Context

The Spendly expense-tracker (Flask app at `app.py`) currently has no data layer.
`database/db.py` is a stub with comments only, and `app.py` defines routes but never
touches a database. This step is the foundation for every subsequent feature
(auth in step 3, profile in step 4, expense CRUD in steps 7–9).

The spec at `database/.claude/specs/01-database-setup.md` requires a plain
`sqlite3` implementation (no ORM, parameterized queries only) exposing three
functions — `get_db()`, `init_db()`, `seed_db()` — and a startup hook in
`app.py` that initializes and seeds the DB inside an `app.app_context()`.

Outcome: on first `python app.py`, a `spendly.db` file is created at the project
root with `users` and `expenses` tables, one demo user, and 8 sample expenses
spanning the 7 fixed categories. Re-running the app does not duplicate seed data.

---

## Files to Change

1. `database/db.py` — replace the stub with a full implementation.
2. `app.py` — add three imports and a startup block.

No new files, no new pip packages (uses `sqlite3` stdlib + already-installed
`werkzeug.security`).

---

## `database/db.py` — Implementation

### Module-level constants

- `DB_PATH = "spendly.db"` — at project root (relative path; matches how
  `app.py` runs from the project root).
- Imports: `sqlite3`, `from datetime import date`,
  `from werkzeug.security import generate_password_hash`.

### `get_db()`

- Open `sqlite3.connect(DB_PATH)`.
- Set `conn.row_factory = sqlite3.Row` (dict-like row access).
- Execute `conn.execute("PRAGMA foreign_keys = ON")` on the returned connection
  (must be set per-connection in SQLite — this is the most error-prone part of
  the spec).
- Return the connection.

### `init_db()`

- Acquire connection via `get_db()`.
- Execute two `CREATE TABLE IF NOT EXISTS` statements inside a single
  transaction; commit; close.

Schema (verbatim from spec §4):

```sql
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      REAL    NOT NULL,
    category    TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    description TEXT,
    created_at  TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

Notes:
- `DEFAULT datetime('now')` needs to be wrapped in parentheses inside
  `CREATE TABLE` (SQLite syntax requirement).
- Idempotent by design — safe to call on every startup.

### `seed_db()`

Idempotency check first:
```python
cur = conn.execute("SELECT COUNT(*) AS n FROM users")
if cur.fetchone()["n"] > 0:
    conn.close()
    return
```

Insert demo user (parameterized):
- name: `"Demo User"`
- email: `"demo@spendly.com"`
- password_hash: `generate_password_hash("demo123")`

Capture `user_id = cur.lastrowid`.

Insert **8** expenses covering all 7 categories from spec §10 (Food, Transport,
Bills, Health, Entertainment, Shopping, Other) — one per category plus one
extra. Dates spread across the current month using
`date.today().replace(day=N).isoformat()` (formatted `YYYY-MM-DD`). Use
`executemany` with a list of tuples for the insert.

Suggested sample rows (representative, not prescriptive — exact amounts/labels
can vary):

| amount | category      | day  | description       |
| ------ | ------------- | ---- | ----------------- |
| 12.50  | Food          | 2    | Lunch             |
| 45.00  | Transport     | 4    | Uber to airport   |
| 110.00 | Bills         | 6    | Electricity       |
| 30.00  | Health        | 9    | Pharmacy          |
| 22.75  | Entertainment | 12   | Movie ticket      |
| 89.99  | Shopping      | 15   | New shoes         |
| 6.50   | Other         | 18   | Misc              |
| 18.00  | Food          | 21   | Groceries top-up  |

Wrap inserts in a transaction; commit; close. Use `?` placeholders only — no
f-strings or `%` formatting in SQL (spec §11).

---

## `app.py` — Changes

Add at top, below the `Flask` import:

```python
from database.db import get_db, init_db, seed_db
```

Add **before** `if __name__ == "__main__":` (so it runs whether started by
`python app.py` or by a WSGI server):

```python
with app.app_context():
    init_db()
    seed_db()
```

Do **not** modify any existing route. `get_db` is imported so future steps can
use it without re-editing `app.py`.

---

## Edge Cases / Things to Get Right

- **PRAGMA per connection**: `foreign_keys = ON` does not persist — must be set
  every time `get_db()` is called. Tests for FK enforcement (spec §13) will
  fail silently otherwise.
- **Parentheses around `datetime('now')`** in `DEFAULT` — without them SQLite
  raises a syntax error.
- **Connection hygiene**: `init_db()` and `seed_db()` both open and close their
  own connections — they do not share a global connection.
- **Idempotent seed**: check `COUNT(*) > 0` on `users` (not `expenses`), since
  the spec ties the demo user to the seed contract.
- **`spendly.db` location**: relative path works because Flask's dev server
  runs with cwd = project root. Keep it relative for now (matches spec wording).
- **`.gitignore`**: `spendly.db` should be ignored. Check the existing
  `.gitignore` during implementation; add the line if absent.

---

## Verification

After implementation:

1. **Cold start**:
   ```powershell
   Remove-Item spendly.db -ErrorAction SilentlyContinue
   python app.py
   ```
   Confirm `spendly.db` is created at project root and Flask boots on port 5001
   without errors.

2. **Schema + seed inspection**:
   ```powershell
   python -c "import sqlite3; c=sqlite3.connect('spendly.db'); print(c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()); print(c.execute('SELECT id,name,email FROM users').fetchall()); print(c.execute('SELECT category,COUNT(*) FROM expenses GROUP BY category').fetchall())"
   ```
   Expect: both tables present, exactly 1 user, all 7 categories represented,
   8 total expenses.

3. **Idempotency**: re-run `python app.py`, then re-run the inspection query.
   User count stays at 1, expense count stays at 8.

4. **FK enforcement** (manual check in a Python REPL):
   ```python
   from database.db import get_db
   conn = get_db()
   conn.execute("INSERT INTO expenses(user_id, amount, category, date) VALUES (?,?,?,?)",
                (9999, 1.0, "Food", "2026-05-27"))
   conn.commit()  # should raise sqlite3.IntegrityError
   ```

5. **Unique email**:
   ```python
   conn.execute("INSERT INTO users(name,email,password_hash) VALUES (?,?,?)",
                ("Dup", "demo@spendly.com", "x"))
   conn.commit()  # should raise sqlite3.IntegrityError
   ```

6. **Definition of Done (spec §14)** — walk the checklist; every item should
   pass after the above commands succeed.
