# Spec: Registration

## Overview
Wire up user registration so visitors can create a Spendly account from the existing `register.html` form. This is the first feature that writes to the `users` table created in Step 1 and is a prerequisite for Login (Step 3) and every authenticated feature that follows. After this step, a new visitor can submit the form, have their password hashed and stored, and be redirected toward sign-in.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()` helper, `werkzeug` password hashing)

## Routes
- `GET /register` — render the registration form (already implemented — must be extended to accept POST) — public
- `POST /register` — validate input, create the user, redirect to login on success or re-render with an error on failure — public

## Database changes
No database changes. The existing `users` table from Step 1 already has `id`, `name`, `email` (UNIQUE), `password_hash`, and `created_at`.

## Templates
- **Create:** none
- **Modify:** `templates/register.html` — keep the existing markup; ensure the form posts to `url_for('register')` instead of the hardcoded `/register`, and surface the `error` variable that the route already passes through (block is already wired)

## Files to change
- `app.py` — change `@app.route("/register")` to accept `GET` and `POST`, add input validation, insert via a new `database/db.py` helper, redirect to `login` on success, re-render with `error` on failure
- `database/db.py` — add two small helpers used by the new route:
  - `get_user_by_email(email)` — returns the row or `None`
  - `create_user(name, email, password)` — hashes the password with `werkzeug.security.generate_password_hash` and inserts the row, returning the new `id`
- `templates/register.html` — replace `action="/register"` with `action="{{ url_for('register') }}"` to match the CLAUDE.md rule about never hardcoding URLs

## Files to create
- None

## New dependencies
No new dependencies. `werkzeug` is already in `requirements.txt`.

## Rules for implementation
- No SQLAlchemy or ORMs — use `sqlite3` via `get_db()` only
- Parameterised queries only — no f-strings or `%` formatting in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash` — never store plaintext
- Use CSS variables — never hardcode hex values (no CSS changes expected in this step, but if any tweaks are needed, pull from `static/css/style.css` tokens)
- All templates extend `base.html`
- DB logic lives in `database/db.py` — the route must only call helpers, never run SQL inline
- Use `url_for()` for every internal link and form action
- Use `abort()` only for true HTTP errors; for form validation failures, re-render `register.html` with an `error` string
- Trim whitespace from `name` and `email`, lowercase `email` before lookup and insert
- Minimum password length: 8 characters (matches the placeholder in the template)
- On success, `redirect(url_for('login'))` — do not auto-log-in the user (that is Step 3)

## Definition of done
- [ ] `GET /register` still renders the form unchanged
- [ ] Submitting the form with valid, unused name + email + 8+ char password creates a row in `users` with a hashed password and redirects to `/login`
- [ ] Submitting with an email that already exists re-renders `register.html` with an inline error message and no new row is inserted
- [ ] Submitting with a missing field re-renders the form with an inline error
- [ ] Submitting with a password shorter than 8 characters re-renders the form with an inline error
- [ ] `register.html` form `action` resolves through `url_for('register')` (verified by viewing page source)
- [ ] Stored `password_hash` is not equal to the plaintext password (verified by inspecting the DB row)
- [ ] No SQL appears inline in `app.py` — all DB access goes through `database/db.py`
- [ ] App still boots on port 5001 with `python app.py` and no errors
