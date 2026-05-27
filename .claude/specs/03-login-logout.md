# Spec: Login and Logout

## Overview
Step 02 lets a visitor create an account; Step 03 lets that account holder actually sign in and out. This feature turns the existing `login.html` form into a working POST handler that verifies a password hash, stashes the user's id in a Flask `session`, and redirects to `/profile`. It also replaces the placeholder `/logout` stub with a real route that clears the session and returns the visitor to the landing page. After this step, "logged-in" is a meaningful concept that Steps 4–9 can rely on.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`)
- Step 2 — Registration (`get_user_by_email`, `create_user`, hashed passwords)

## Routes
- `POST /login` — verify submitted email + password, set `session["user_id"]`, redirect to `/profile`; re-render with an error on failure — public (the existing `GET /login` stays as it is, now sharing the same view function)
- `GET /logout` — clear the session and redirect to `/` — logged-in (but tolerant of being hit when no session exists — should still redirect cleanly)

## Database changes
No database changes. Authentication uses the existing `users.password_hash` column.

## Templates
- **Create:** none
- **Modify:** `templates/login.html` — swap the hardcoded `action="/login"` for `action="{{ url_for('login') }}"`. The `{% if error %}` block and the `url_for('register')` link in the auth switch are already wired correctly.

## Files to change
- `app.py`:
  - Set `app.secret_key` (loaded from `SPENDLY_SECRET_KEY` env var, with a development fallback) so `session` works
  - Extend Flask imports with `session`
  - Extend `database.db` imports with `get_user_by_email`
  - Convert `@app.route("/login")` into a `methods=["GET", "POST"]` handler with validation, password verification, and session set
  - Replace the `/logout` stub with a real implementation that pops `user_id` from the session and redirects to `landing`
- `database/db.py`: no new helpers required — `get_user_by_email` from Step 2 is reused. Add a top-level `from werkzeug.security import check_password_hash` import (`generate_password_hash` is already imported).
- `templates/login.html`: change form `action` to `url_for('login')`.

## Files to create
- None.

## New dependencies
No new dependencies. `werkzeug.security.check_password_hash` ships with the already-installed `werkzeug==3.1.6`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — reuse `get_user_by_email` from Step 2, do not write inline SQL in `app.py`
- Passwords verified with `werkzeug.security.check_password_hash` — never compare hashes by string equality
- Use CSS variables — never hardcode hex values (no CSS changes expected in this step)
- All templates extend `base.html`
- Use `url_for()` for every internal link and form action
- Normalise the submitted email with `.strip().lower()` before the lookup so casing matches the lowercase storage from Step 2
- Do NOT strip the submitted password
- On any auth failure (missing field, unknown email, wrong password) re-render `login.html` with a generic error string — do not disclose which field was wrong, to avoid account enumeration
- `app.secret_key` must come from `os.environ.get("SPENDLY_SECRET_KEY")` with a clearly-labelled dev fallback (e.g. `"dev-only-change-me"`); never hardcode a production secret
- The `/logout` route must not crash if called without a session — `session.pop("user_id", None)` is the right pattern
- Stub routes for Steps 4/7/8/9 stay untouched

## Definition of done
- [ ] `GET /login` still renders the form unchanged
- [ ] Submitting valid credentials (email + password registered in Step 2) sets `session["user_id"]` and redirects to `/profile`
- [ ] Submitting an unknown email re-renders `login.html` with a generic "Invalid email or password." error
- [ ] Submitting a known email with the wrong password shows the same generic error (no enumeration)
- [ ] Submitting a missing field shows an inline error and does not query the DB unnecessarily (validate first)
- [ ] Email comparison is case-insensitive (logging in as `ALICE@TEST.COM` after registering `alice@test.com` succeeds)
- [ ] `login.html` form action resolves through `url_for('login')` (verified by viewing page source after a view-function rename smoke test, or just by inspection)
- [ ] Visiting `/logout` while logged in clears `session["user_id"]` and redirects to `/`
- [ ] Visiting `/logout` without a session also redirects to `/` and does not raise
- [ ] `app.secret_key` is set from the `SPENDLY_SECRET_KEY` env var when present, otherwise from a clearly-named dev fallback
- [ ] No SQL appears inline in `app.py` (`grep -n "SELECT\|INSERT" app.py` returns nothing)
- [ ] App still boots on port 5001 with `python app.py` and no errors
