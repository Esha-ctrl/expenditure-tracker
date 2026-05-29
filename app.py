import os
from datetime import date, datetime

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db, set_user_currency
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SPENDLY_SECRET_KEY", "dev-only-change-me")

def _first_of_month_n_ago(n, ref):
    """Return ISO date string for the 1st of the month n months before ref."""
    month = ref.month - n
    year = ref.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    return date(year, month, 1).isoformat()


CURRENCIES = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "AUD": "A$",
    "CAD": "C$",
    "SGD": "S$",
    "CHF": "Fr",
    "CNY": "¥",
}

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    if "user_id" in session:
        return redirect(url_for("profile"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("register.html")

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not name or not email or not password:
        return render_template("register.html", error="All fields are required.")
    if len(password) < 8:
        return render_template(
            "register.html", error="Password must be at least 8 characters."
        )

    new_id = create_user(name, email, password)
    if new_id is None:
        return render_template(
            "register.html", error="An account with that email already exists."
        )

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html")

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not email or not password:
        return render_template("login.html", error="All fields are required.")

    user = get_user_by_email(email)
    try:
        ok = user is not None and check_password_hash(user["password_hash"], password)
    except (ValueError, TypeError):
        ok = False

    if not ok:
        return render_template("login.html", error="Invalid email or password.")

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/settings/currency", methods=["POST"])
def update_currency():
    if "user_id" not in session:
        return redirect(url_for("login"))
    code = request.form.get("currency", "INR")
    if code in CURRENCIES:
        set_user_currency(session["user_id"], code)
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = get_user_by_id(session["user_id"])
    if user is None:
        session.pop("user_id", None)
        session.pop("user_name", None)
        session.pop("user_email", None)
        return redirect(url_for("login"))

    # Parse and validate date filter params
    raw_from = request.args.get("date_from", "").strip()
    raw_to = request.args.get("date_to", "").strip()

    date_from = date_to = None
    error = None

    if raw_from:
        try:
            datetime.strptime(raw_from, "%Y-%m-%d")
            date_from = raw_from
        except ValueError:
            pass

    if raw_to:
        try:
            datetime.strptime(raw_to, "%Y-%m-%d")
            date_to = raw_to
        except ValueError:
            pass

    if date_from and date_to and date_from > date_to:
        error = "Start date must be before end date."
        date_from = date_to = None

    # Compute preset date strings
    today = date.today()
    today_str = today.isoformat()
    this_month_from = today.replace(day=1).isoformat()
    three_mo_from = _first_of_month_n_ago(3, today)
    six_mo_from = _first_of_month_n_ago(6, today)

    # Detect which preset (if any) is active
    if not date_from and not date_to:
        active_preset = "all"
    elif date_from == this_month_from and date_to == today_str:
        active_preset = "this_month"
    elif date_from == three_mo_from and date_to == today_str:
        active_preset = "3mo"
    elif date_from == six_mo_from and date_to == today_str:
        active_preset = "6mo"
    else:
        active_preset = None

    currency_code = user.get("preferred_currency", "INR")
    currency_symbol = CURRENCIES.get(currency_code, "₹")

    stats = get_summary_stats(session["user_id"], date_from=date_from, date_to=date_to)
    expenses = get_recent_transactions(session["user_id"], limit=10, date_from=date_from, date_to=date_to)
    categories = get_category_breakdown(session["user_id"], date_from=date_from, date_to=date_to)

    stats["currency_symbol"] = currency_symbol

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        expenses=expenses,
        categories=categories,
        error=error,
        date_from=date_from,
        date_to=date_to,
        date_today=today_str,
        this_month_from=this_month_from,
        three_mo_from=three_mo_from,
        six_mo_from=six_mo_from,
        active_preset=active_preset,
        filter_active=bool(date_from or date_to),
        currencies=CURRENCIES,
        currency_code=currency_code,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5001)
