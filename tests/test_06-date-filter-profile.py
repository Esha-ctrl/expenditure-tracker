"""
Tests for Step 6: Date Filter on the /profile route.

Spec: .claude/specs/06-date-filter-profile.md

Coverage:
- Auth guard (unauthenticated redirects to /login)
- All-time fallback (no params = unfiltered)
- Valid custom date range filters all three data sections
- Single-bound filters (only date_from, only date_to)
- date_from > date_to shows flash error and falls back to unfiltered view
- Malformed date strings do not crash the app
- Preset date ranges (This Month, Last 3 Months, Last 6 Months, All Time)
- User with no expenses in range sees zeros, no errors
- Template landmarks: filter bar and preset buttons are rendered
- DB side effects: inserted expenses are filtered correctly by date
"""

import sqlite3
from datetime import date, timedelta

import pytest

from app import app as flask_app
from database.db import get_db, init_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_day_of_month(d: date) -> date:
    return d.replace(day=1)


def _months_ago_first(today: date, n: int) -> date:
    """Return the first day of the month that is n months before today."""
    m = today.month - n
    y = today.year
    if m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    """
    Isolated Flask app using an on-disk SQLite DB in a temp directory.
    We cannot use ':memory:' directly because get_db() always opens DB_PATH,
    so we patch the DB_PATH used by the db module to a temp file.
    """
    db_file = str(tmp_path / "test_spendly.db")

    import database.db as db_module
    original_path = db_module.DB_PATH
    db_module.DB_PATH = db_file

    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })

    with flask_app.app_context():
        init_db()
        yield flask_app

    db_module.DB_PATH = original_path


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def registered_user(app):
    """Register a fresh test user and return (email, password, user_id)."""
    import database.db as db_module
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    from werkzeug.security import generate_password_hash
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "testuser@example.com", generate_password_hash("testpass123")),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return ("testuser@example.com", "testpass123", user_id)


@pytest.fixture
def auth_client(client, registered_user):
    """Test client already logged in as the registered test user."""
    email, password, _ = registered_user
    client.post("/login", data={"email": email, "password": password})
    return client


@pytest.fixture
def auth_client_with_expenses(client, registered_user, app):
    """
    Logged-in client whose user has a predictable set of expenses
    spanning three distinct dates:
      - 2020-01-15  (clearly in the past, outside any recent preset)
      - 2020-06-20  (clearly in the past)
      - <today>     (always within every preset window)
    """
    email, password, user_id = registered_user

    import database.db as db_module
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    today_str = date.today().isoformat()

    expenses = [
        (user_id, 10.00, "Food",      "2020-01-15", "Old lunch"),
        (user_id, 20.00, "Transport", "2020-06-20", "Old taxi"),
        (user_id, 50.00, "Bills",     today_str,    "Today bill"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        expenses,
    )
    conn.commit()
    conn.close()

    client.post("/login", data={"email": email, "password": password})
    return client, user_id


# ---------------------------------------------------------------------------
# Auth guard tests
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_unauthenticated_get_profile_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302, "Unauthenticated /profile must redirect"
        assert "/login" in response.headers["Location"], (
            "Redirect must point to /login"
        )

    def test_unauthenticated_get_profile_with_date_params_redirects(self, client):
        response = client.get("/profile?date_from=2024-01-01&date_to=2024-12-31")
        assert response.status_code == 302, (
            "Unauthenticated /profile with date params must still redirect"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect must point to /login"
        )

    def test_unauthenticated_follows_redirect_to_login_page(self, client):
        response = client.get("/profile", follow_redirects=True)
        assert response.status_code == 200
        assert b"Login" in response.data or b"login" in response.data, (
            "Following redirect should land on login page"
        )


# ---------------------------------------------------------------------------
# All-time fallback (no params)
# ---------------------------------------------------------------------------

class TestAllTimeFallback:
    def test_profile_no_params_returns_200(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200, (
            "Authenticated /profile with no params must return 200"
        )

    def test_profile_no_params_shows_all_expenses(self, auth_client_with_expenses):
        client, _ = auth_client_with_expenses
        response = client.get("/profile")
        assert response.status_code == 200
        # All three expense descriptions must appear (all-time = no filter)
        assert b"Old lunch" in response.data, "Old expense from 2020-01-15 must appear"
        assert b"Old taxi" in response.data, "Old expense from 2020-06-20 must appear"
        assert b"Today bill" in response.data, "Today expense must appear"

    def test_profile_no_params_all_time_preset_active(self, auth_client_with_expenses):
        client, _ = auth_client_with_expenses
        response = client.get("/profile")
        assert response.status_code == 200
        # The template must reflect that "all" is the active preset
        # The spec says active_preset="all" is passed to the template
        assert b"All Time" in response.data, (
            "All Time preset button must be present and rendered when no filter active"
        )

    def test_profile_no_params_no_filter_active_class(self, auth_client_with_expenses):
        client, _ = auth_client_with_expenses
        response = client.get("/profile")
        assert response.status_code == 200
        # The page must not show a date-range error
        assert b"Start date must be before end date" not in response.data, (
            "No error should appear when no date params are provided"
        )


# ---------------------------------------------------------------------------
# Valid custom date range
# ---------------------------------------------------------------------------

class TestCustomDateRange:
    def test_valid_range_includes_expenses_within_bounds(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        # 2020-01-01 to 2020-01-31 should include only "Old lunch" on 2020-01-15
        response = client.get(
            "/profile?date_from=2020-01-01&date_to=2020-01-31"
        )
        assert response.status_code == 200
        assert b"Old lunch" in response.data, (
            "Expense on 2020-01-15 must appear when range is 2020-01-01..2020-01-31"
        )

    def test_valid_range_excludes_expenses_outside_bounds(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        # 2020-01-01 to 2020-01-31 should NOT include "Old taxi" (2020-06-20)
        response = client.get(
            "/profile?date_from=2020-01-01&date_to=2020-01-31"
        )
        assert response.status_code == 200
        assert b"Old taxi" not in response.data, (
            "Expense on 2020-06-20 must NOT appear when range is 2020-01-01..2020-01-31"
        )

    def test_valid_range_inclusive_lower_bound(self, auth_client_with_expenses):
        client, _ = auth_client_with_expenses
        # date_from=2020-01-15 means that day itself is included
        response = client.get(
            "/profile?date_from=2020-01-15&date_to=2020-01-15"
        )
        assert response.status_code == 200
        assert b"Old lunch" in response.data, (
            "date_from bound must be inclusive (expense on exact boundary date)"
        )

    def test_valid_range_inclusive_upper_bound(self, auth_client_with_expenses):
        client, _ = auth_client_with_expenses
        # date_to=2020-06-20 means that day itself is included
        response = client.get(
            "/profile?date_from=2020-06-20&date_to=2020-06-20"
        )
        assert response.status_code == 200
        assert b"Old taxi" in response.data, (
            "date_to bound must be inclusive (expense on exact boundary date)"
        )

    def test_valid_range_returns_200(self, auth_client):
        response = auth_client.get(
            "/profile?date_from=2024-01-01&date_to=2024-12-31"
        )
        assert response.status_code == 200, (
            "Valid date range must return HTTP 200"
        )

    def test_valid_range_no_error_shown(self, auth_client):
        response = auth_client.get(
            "/profile?date_from=2024-01-01&date_to=2024-12-31"
        )
        assert b"Start date must be before end date" not in response.data, (
            "No validation error should appear for a valid date range"
        )

    def test_empty_range_shows_zero_total(self, auth_client_with_expenses):
        client, _ = auth_client_with_expenses
        # A range with no matching expenses should show 0.00 total, no errors
        response = client.get(
            "/profile?date_from=2000-01-01&date_to=2000-01-02"
        )
        assert response.status_code == 200, (
            "Profile page with empty result range must still return 200"
        )
        assert b"0.00" in response.data, (
            "Total must show 0.00 when no expenses fall in the selected range"
        )


# ---------------------------------------------------------------------------
# Single-bound filters
# ---------------------------------------------------------------------------

class TestSingleBoundFilters:
    def test_only_date_from_excludes_earlier_expenses(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        # date_from=2020-06-01 should exclude "Old lunch" (2020-01-15)
        response = client.get("/profile?date_from=2020-06-01")
        assert response.status_code == 200
        assert b"Old lunch" not in response.data, (
            "Expense before date_from must be excluded when only date_from is given"
        )

    def test_only_date_from_includes_expenses_on_or_after(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        # date_from=2020-06-01 must include "Old taxi" (2020-06-20)
        response = client.get("/profile?date_from=2020-06-01")
        assert response.status_code == 200
        assert b"Old taxi" in response.data, (
            "Expense on or after date_from must be included when only date_from is given"
        )

    def test_only_date_to_excludes_later_expenses(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        today_str = date.today().isoformat()
        # date_to=2020-12-31 should exclude today's expense
        response = client.get("/profile?date_to=2020-12-31")
        assert response.status_code == 200
        assert b"Today bill" not in response.data, (
            "Expense after date_to must be excluded when only date_to is given"
        )

    def test_only_date_to_includes_expenses_on_or_before(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        # date_to=2020-06-20 must include "Old taxi" (2020-06-20)
        response = client.get("/profile?date_to=2020-06-20")
        assert response.status_code == 200
        assert b"Old taxi" in response.data, (
            "Expense on or before date_to must be included when only date_to is given"
        )

    def test_only_date_from_returns_200(self, auth_client):
        response = auth_client.get("/profile?date_from=2024-01-01")
        assert response.status_code == 200, (
            "Profile with only date_from must return 200"
        )

    def test_only_date_to_returns_200(self, auth_client):
        response = auth_client.get("/profile?date_to=2024-12-31")
        assert response.status_code == 200, (
            "Profile with only date_to must return 200"
        )


# ---------------------------------------------------------------------------
# date_from > date_to validation error
# ---------------------------------------------------------------------------

class TestDateOrderValidation:
    def test_date_from_after_date_to_shows_flash_error(self, auth_client):
        response = auth_client.get(
            "/profile?date_from=2024-12-31&date_to=2024-01-01"
        )
        assert response.status_code == 200, (
            "Invalid date order must still return 200, not crash"
        )
        assert b"Start date must be before end date" in response.data, (
            "Flash error message must appear when date_from > date_to"
        )

    def test_date_from_after_date_to_falls_back_to_unfiltered(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        # date_from > date_to => fall back to all-time view, all expenses visible
        response = client.get(
            "/profile?date_from=2025-01-01&date_to=2020-01-01"
        )
        assert response.status_code == 200
        assert b"Old lunch" in response.data, (
            "Old expense must appear in unfiltered fallback after invalid date order"
        )
        assert b"Old taxi" in response.data, (
            "Old expense must appear in unfiltered fallback after invalid date order"
        )
        assert b"Today bill" in response.data, (
            "Today's expense must appear in unfiltered fallback after invalid date order"
        )

    def test_date_from_equal_to_date_to_is_valid(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        # date_from == date_to is a single-day range — valid, not an error
        response = client.get(
            "/profile?date_from=2020-01-15&date_to=2020-01-15"
        )
        assert response.status_code == 200
        assert b"Start date must be before end date" not in response.data, (
            "Equal date_from and date_to must be treated as a valid single-day range"
        )
        assert b"Old lunch" in response.data, (
            "Expense on the single-day range boundary must appear"
        )


# ---------------------------------------------------------------------------
# Malformed date strings — must not crash the app
# ---------------------------------------------------------------------------

class TestMalformedDates:
    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "2024-13-01",
        "2024/01/01",
        "01-01-2024",
        "yesterday",
        "2024-00-00",
        "",
        "2024-1-1",
        "abc",
        "2024-02-30",
    ])
    def test_malformed_date_from_does_not_crash(self, auth_client, bad_date):
        response = auth_client.get(f"/profile?date_from={bad_date}")
        assert response.status_code == 200, (
            f"Malformed date_from='{bad_date}' must not crash the app (expected 200)"
        )

    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "2024-13-01",
        "2024/12/31",
        "31-12-2024",
        "tomorrow",
        "2024-00-00",
        "",
        "2024-2-30",
    ])
    def test_malformed_date_to_does_not_crash(self, auth_client, bad_date):
        response = auth_client.get(f"/profile?date_to={bad_date}")
        assert response.status_code == 200, (
            f"Malformed date_to='{bad_date}' must not crash the app (expected 200)"
        )

    def test_both_malformed_falls_back_to_unfiltered(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        response = client.get(
            "/profile?date_from=not-a-date&date_to=also-not-a-date"
        )
        assert response.status_code == 200
        # Fallback to all-time: all expenses visible
        assert b"Old lunch" in response.data, (
            "All expenses must show when both date params are malformed (unfiltered fallback)"
        )
        assert b"Old taxi" in response.data, (
            "All expenses must show when both date params are malformed (unfiltered fallback)"
        )

    def test_malformed_date_from_valid_date_to_falls_back(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        # Only date_to valid; malformed date_from treated as absent
        response = client.get(
            "/profile?date_from=not-a-date&date_to=2020-01-31"
        )
        assert response.status_code == 200, (
            "Malformed date_from with valid date_to must return 200"
        )

    def test_valid_date_from_malformed_date_to_falls_back(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        # Only date_from valid; malformed date_to treated as absent
        response = client.get(
            "/profile?date_from=2020-01-01&date_to=not-a-date"
        )
        assert response.status_code == 200, (
            "Valid date_from with malformed date_to must return 200"
        )


# ---------------------------------------------------------------------------
# Preset date ranges
# ---------------------------------------------------------------------------

class TestPresetDateRanges:
    def test_this_month_preset_excludes_old_expenses(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        today = date.today()
        date_from = today.replace(day=1).isoformat()
        date_to = today.isoformat()
        response = client.get(
            f"/profile?date_from={date_from}&date_to={date_to}"
        )
        assert response.status_code == 200
        # Old expenses from 2020 must NOT appear under "This Month" filter
        assert b"Old lunch" not in response.data, (
            "2020-01-15 expense must not appear in This Month filter"
        )
        assert b"Old taxi" not in response.data, (
            "2020-06-20 expense must not appear in This Month filter"
        )

    def test_this_month_preset_includes_today_expense(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        today = date.today()
        date_from = today.replace(day=1).isoformat()
        date_to = today.isoformat()
        response = client.get(
            f"/profile?date_from={date_from}&date_to={date_to}"
        )
        assert response.status_code == 200
        assert b"Today bill" in response.data, (
            "Today's expense must appear in This Month filter"
        )

    def test_last_3_months_preset_excludes_very_old_expenses(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        today = date.today()
        date_from = _months_ago_first(today, 3).isoformat()
        date_to = today.isoformat()
        response = client.get(
            f"/profile?date_from={date_from}&date_to={date_to}"
        )
        assert response.status_code == 200
        # 2020 expenses are well outside a 3-month window from today
        assert b"Old lunch" not in response.data, (
            "2020-01-15 expense must not appear in Last 3 Months filter"
        )
        assert b"Old taxi" not in response.data, (
            "2020-06-20 expense must not appear in Last 3 Months filter"
        )

    def test_last_3_months_preset_includes_today_expense(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        today = date.today()
        date_from = _months_ago_first(today, 3).isoformat()
        date_to = today.isoformat()
        response = client.get(
            f"/profile?date_from={date_from}&date_to={date_to}"
        )
        assert response.status_code == 200
        assert b"Today bill" in response.data, (
            "Today's expense must appear in Last 3 Months filter"
        )

    def test_last_6_months_preset_excludes_very_old_expenses(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        today = date.today()
        date_from = _months_ago_first(today, 6).isoformat()
        date_to = today.isoformat()
        response = client.get(
            f"/profile?date_from={date_from}&date_to={date_to}"
        )
        assert response.status_code == 200
        assert b"Old lunch" not in response.data, (
            "2020-01-15 expense must not appear in Last 6 Months filter"
        )
        assert b"Old taxi" not in response.data, (
            "2020-06-20 expense must not appear in Last 6 Months filter"
        )

    def test_last_6_months_preset_includes_today_expense(
        self, auth_client_with_expenses
    ):
        client, _ = auth_client_with_expenses
        today = date.today()
        date_from = _months_ago_first(today, 6).isoformat()
        date_to = today.isoformat()
        response = client.get(
            f"/profile?date_from={date_from}&date_to={date_to}"
        )
        assert response.status_code == 200
        assert b"Today bill" in response.data, (
            "Today's expense must appear in Last 6 Months filter"
        )

    def test_all_time_preset_url_has_no_date_params(self, auth_client):
        # The "All Time" preset must produce a clean /profile URL (no date params)
        # We verify that /profile with no params returns 200 and is the all-time view
        response = auth_client.get("/profile")
        assert response.status_code == 200
        assert b"Start date must be before end date" not in response.data, (
            "All Time (no params) must not show any date validation error"
        )

    def test_all_time_shows_all_expenses(self, auth_client_with_expenses):
        client, _ = auth_client_with_expenses
        response = client.get("/profile")
        assert response.status_code == 200
        assert b"Old lunch" in response.data, "All Time must show all expenses"
        assert b"Old taxi" in response.data, "All Time must show all expenses"
        assert b"Today bill" in response.data, "All Time must show all expenses"

    def test_preset_buttons_rendered_in_template(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200
        assert b"This Month" in response.data, (
            "'This Month' preset button must be rendered"
        )
        assert b"Last 3 Months" in response.data, (
            "'Last 3 Months' preset button must be rendered"
        )
        assert b"Last 6 Months" in response.data, (
            "'Last 6 Months' preset button must be rendered"
        )
        assert b"All Time" in response.data, (
            "'All Time' preset button must be rendered"
        )


# ---------------------------------------------------------------------------
# Empty result set — user has no expenses in selected range
# ---------------------------------------------------------------------------

class TestEmptyResultRange:
    def test_no_expenses_in_range_returns_200(self, auth_client):
        # Fresh user has no expenses at all; any range returns empty results
        response = auth_client.get(
            "/profile?date_from=2024-01-01&date_to=2024-01-31"
        )
        assert response.status_code == 200, (
            "Empty result range must still return HTTP 200"
        )

    def test_no_expenses_in_range_shows_zero_total(self, auth_client):
        response = auth_client.get(
            "/profile?date_from=2024-01-01&date_to=2024-01-31"
        )
        assert response.status_code == 200
        assert b"0.00" in response.data, (
            "Total spent must be 0.00 when no expenses exist in the range"
        )

    def test_no_expenses_in_range_shows_zero_transactions(self, auth_client):
        response = auth_client.get(
            "/profile?date_from=2024-01-01&date_to=2024-01-31"
        )
        assert response.status_code == 200
        # The transaction count should be 0 — rendered as "0" somewhere on the page
        assert b"0" in response.data, (
            "Transaction count must be 0 when no expenses exist in the range"
        )

    def test_no_expenses_range_shows_rupee_symbol(self, auth_client):
        # Spec: all amounts continue to display the currency symbol regardless of filter
        response = auth_client.get(
            "/profile?date_from=2024-01-01&date_to=2024-01-31"
        )
        assert response.status_code == 200
        # Default currency is INR; rupee symbol must still appear
        rupee = "₹".encode("utf-8")
        assert rupee in response.data, (
            "Currency symbol (₹) must appear even when no expenses are in range"
        )

    def test_no_expenses_in_range_no_crash_no_error_message(self, auth_client):
        response = auth_client.get(
            "/profile?date_from=2030-01-01&date_to=2030-12-31"
        )
        assert response.status_code == 200, (
            "Future date range with no expenses must not crash"
        )
        assert b"Start date must be before end date" not in response.data, (
            "A valid future range must not trigger a date-order error"
        )


# ---------------------------------------------------------------------------
# DB side-effects — verify via direct DB query that filter is applied correctly
# ---------------------------------------------------------------------------

class TestDBSideEffects:
    def test_filtered_transactions_match_db_query(
        self, auth_client_with_expenses, app
    ):
        """
        Insert expenses with known dates, apply a filter, then independently
        query the DB to confirm the in-range count matches what the route shows.
        """
        client, user_id = auth_client_with_expenses

        import database.db as db_module
        conn = sqlite3.connect(db_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        # Count how many expenses fall in the range 2020-01-01..2020-12-31
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM expenses "
            "WHERE user_id = ? AND date >= ? AND date <= ?",
            (user_id, "2020-01-01", "2020-12-31"),
        ).fetchone()
        conn.close()

        expected_count = row["n"]
        assert expected_count == 2, (
            "Fixture should have inserted 2 expenses in year 2020"
        )

        response = client.get(
            "/profile?date_from=2020-01-01&date_to=2020-12-31"
        )
        assert response.status_code == 200
        # Both 2020 expenses must appear, today's expense must not
        assert b"Old lunch" in response.data
        assert b"Old taxi" in response.data
        assert b"Today bill" not in response.data, (
            "Today's expense must be excluded from 2020-only filter"
        )

    def test_summary_stats_total_matches_filtered_sum(
        self, auth_client_with_expenses, app
    ):
        """
        The summary stats total must equal the sum of only the filtered expenses.
        """
        client, user_id = auth_client_with_expenses

        import database.db as db_module
        conn = sqlite3.connect(db_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses "
            "WHERE user_id = ? AND date >= ? AND date <= ?",
            (user_id, "2020-01-01", "2020-01-31"),
        ).fetchone()
        conn.close()

        expected_total = row["total"]
        # Only the 2020-01-15 expense (10.00) should be in this range
        assert expected_total == 10.00, (
            "Only the 10.00 expense on 2020-01-15 should be in range 2020-01-01..2020-01-31"
        )

        response = client.get(
            "/profile?date_from=2020-01-01&date_to=2020-01-31"
        )
        assert response.status_code == 200
        assert b"10.00" in response.data, (
            "Summary stat total must reflect only expenses within the date filter"
        )

    def test_category_breakdown_only_shows_filtered_categories(
        self, auth_client_with_expenses, app
    ):
        """
        When filtering to a range that only contains one category, the breakdown
        should reflect that single category and not others outside the range.
        """
        client, user_id = auth_client_with_expenses

        # 2020-01-01..2020-01-31 contains only "Food" category (Old lunch)
        response = client.get(
            "/profile?date_from=2020-01-01&date_to=2020-01-31"
        )
        assert response.status_code == 200
        # "Food" must appear in the breakdown
        assert b"Food" in response.data, (
            "Food category must appear in breakdown for 2020-01-01..2020-01-31 range"
        )
        # "Transport" from 2020-06-20 must NOT appear in the breakdown
        assert b"Transport" not in response.data or b"Old taxi" not in response.data, (
            "Transport category should not appear in breakdown for Jan 2020 only range"
        )


# ---------------------------------------------------------------------------
# Template landmarks
# ---------------------------------------------------------------------------

class TestTemplateLandmarks:
    def test_profile_page_renders_filter_bar(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200
        # The filter bar must be present — checking for date input fields
        assert b'type="date"' in response.data or b"date_from" in response.data, (
            "Filter bar with date inputs must be rendered on the profile page"
        )

    def test_profile_page_has_apply_button(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200
        # The "Apply" button for the custom range form must be present
        assert b"Apply" in response.data, (
            "Custom range Apply button must be present in the filter bar"
        )

    def test_profile_page_extends_base_template(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200
        # base.html typically includes common nav or html structure landmarks
        assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data, (
            "Profile page must render a full HTML document (extends base.html)"
        )

    def test_profile_page_shows_currency_symbol(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200
        rupee = "₹".encode("utf-8")
        assert rupee in response.data, (
            "Default INR currency symbol (₹) must appear on the profile page"
        )

    def test_profile_page_with_active_filter_shows_date_values(self, auth_client):
        response = auth_client.get(
            "/profile?date_from=2024-03-01&date_to=2024-03-31"
        )
        assert response.status_code == 200
        # The active date range values must be reflected in the template
        assert b"2024-03-01" in response.data, (
            "Active date_from value must appear in rendered template"
        )
        assert b"2024-03-31" in response.data, (
            "Active date_to value must appear in rendered template"
        )
