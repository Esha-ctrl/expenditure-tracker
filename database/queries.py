from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
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
        }
    finally:
        conn.close()


def get_summary_stats(user_id):
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS n "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        total = totals["total"] if totals is not None else 0
        count = totals["n"] if totals is not None else 0
        top_category = top["category"] if top is not None else "—"
        return {
            "total_spent": f"{total:.2f}",
            "transaction_count": count,
            "top_category": top_category,
            "currency_symbol": "₹",
        }
    finally:
        conn.close()


def get_recent_transactions(user_id, limit=10):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, date, description, category, amount "
            "FROM expenses WHERE user_id = ? "
            "ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
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


def get_category_breakdown(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category ORDER BY total DESC",
            (user_id,),
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
