from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email, preferred_currency, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        name = row["name"] or ""
        parts = [p for p in name.split() if p]
        if parts:
            initials = "".join(p[0] for p in parts[:2]).upper()
        else:
            initials = "?"
        member_since = datetime.fromisoformat(row["created_at"]).strftime("%B %Y")
        return {
            "name": name,
            "email": row["email"],
            "initials": initials,
            "member_since": member_since,
            "preferred_currency": row["preferred_currency"] or "INR",
        }
    finally:
        conn.close()


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()
    try:
        # Clauses must always be hardcoded strings — never put user input here.
        # All user-supplied values go into params as ? placeholders only.
        clauses = ["user_id = ?"]
        params = [user_id]
        if date_from:
            clauses.append("date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("date <= ?")
            params.append(date_to)
        where = " AND ".join(clauses)
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS n "
            "FROM expenses WHERE " + where,
            params,
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE " + where + " "
            "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            params,
        ).fetchone()
        total = totals["total"] if totals is not None else 0
        count = totals["n"] if totals is not None else 0
        top_category = top["category"] if top is not None else "—"
        return {
            "total_spent": f"{total:.2f}",
            "transaction_count": count,
            "top_category": top_category,
        }
    finally:
        conn.close()


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()
    try:
        clauses = ["user_id = ?"]
        params = [user_id]
        if date_from:
            clauses.append("date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("date <= ?")
            params.append(date_to)
        where = " AND ".join(clauses)
        params.append(limit)
        rows = conn.execute(
            "SELECT id, date, description, category, amount "
            "FROM expenses WHERE " + where + " "
            "ORDER BY date DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
        result = []
        for row in rows:
            dt = datetime.strptime(row["date"], "%Y-%m-%d")
            formatted_date = dt.strftime("%B ") + str(dt.day) + dt.strftime(", %Y")
            result.append({
                "date": formatted_date,
                "description": row["description"],
                "category": row["category"],
                "amount": f"{row['amount']:.2f}",
            })
        return result
    finally:
        conn.close()


def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()
    try:
        clauses = ["user_id = ?"]
        params = [user_id]
        if date_from:
            clauses.append("date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("date <= ?")
            params.append(date_to)
        where = " AND ".join(clauses)
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE " + where + " GROUP BY category ORDER BY total DESC",
            params,
        ).fetchall()
        if not rows:
            return []
        totals = [(row["category"], row["total"] or 0) for row in rows]
        grand_total = sum(t for _, t in totals)
        if grand_total <= 0:
            return []
        pcts = [round(100 * t / grand_total) for _, t in totals]
        remainder = 100 - sum(pcts)
        if pcts:
            pcts[0] += remainder
        result = []
        for (name, total), pct in zip(totals, pcts):
            snapped = max(5, round(pct / 5) * 5)
            if snapped > 100:
                snapped = 100
            result.append({
                "name": name,
                "total": f"{total:.2f}",
                "percent_bucket": snapped,
            })
        return result
    finally:
        conn.close()
