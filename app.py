import os

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db

app = Flask(__name__)
app.secret_key = os.environ.get("SPENDLY_SECRET_KEY", "dev-only-change-me")

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

    name = session.get("user_name", "")
    email = session.get("user_email", "")
    initials = "".join(part[0] for part in name.split() if part)[:2].upper() or "?"

    user = {
        "name": name,
        "email": email,
        "initials": initials,
        "member_since": "January 2026",
    }

    stats = {
        "total_spent": "334.74",
        "transaction_count": 8,
        "top_category": "Bills",
        "currency_symbol": "₹",
    }

    expenses = [
        {"date": "May 21, 2026", "description": "Groceries top-up",
         "category": "Food", "amount": "18.00"},
        {"date": "May 18, 2026", "description": "Electricity bill",
         "category": "Bills", "amount": "62.40"},
        {"date": "May 15, 2026", "description": "New running shoes",
         "category": "Shopping", "amount": "89.99"},
        {"date": "May 12, 2026", "description": "Movie ticket",
         "category": "Entertainment", "amount": "22.75"},
        {"date": "May 9, 2026", "description": "Pharmacy",
         "category": "Health", "amount": "30.00"},
        {"date": "May 5, 2026", "description": "Metro card refill",
         "category": "Transport", "amount": "45.00"},
        {"date": "May 3, 2026", "description": "Internet bill",
         "category": "Bills", "amount": "47.60"},
        {"date": "May 1, 2026", "description": "Coffee with a friend",
         "category": "Other", "amount": "9.00"},
    ]

    categories = [
        {"name": "Bills",         "total": "110.00", "percent_bucket": 35},
        {"name": "Shopping",      "total": "89.99",  "percent_bucket": 25},
        {"name": "Transport",     "total": "45.00",  "percent_bucket": 15},
        {"name": "Health",        "total": "30.00",  "percent_bucket": 10},
        {"name": "Entertainment", "total": "22.75",  "percent_bucket": 10},
        {"name": "Food",          "total": "18.00",  "percent_bucket": 5},
        {"name": "Other",         "total": "9.00",   "percent_bucket": 5},
    ]

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        expenses=expenses,
        categories=categories,
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
    app.run(debug=True, port=5001)
