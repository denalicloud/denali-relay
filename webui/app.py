#!/usr/bin/env python3
"""
WebUI per relay SMTP — Denali PRO SA
Login con credenziali SASL, visualizzazione invii per utente.
"""

import sqlite3
import subprocess
import logging
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, session,
    redirect, url_for, g
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "changeme-in-production")

DB_FILE = "/data/relay.db"
SASL_PASSWD = "/etc/relay/sasl_passwd"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def verify_sasl_credentials(username, password):
    """Verifica le credenziali leggendo sasl_passwd (tab-separated)."""
    try:
        with open(SASL_PASSWD, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    u, p = parts
                    if u == username and p == password:
                        return True
    except Exception as e:
        logging.error(f"Error reading sasl_passwd: {e}")
    return False

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if verify_sasl_credentials(username, password):
            session["username"] = username
            logging.info(f"Login OK: {username}")
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid credentials"
            logging.warning(f"Login failed: {username}")
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    username = session["username"]
    db = get_db()

    # Filtri
    status_filter = request.args.get("status", "all")
    days = int(request.args.get("days", 30))
    page = int(request.args.get("page", 1))
    per_page = 50

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    # Query messaggi
    where = "WHERE sasl_username = ? AND timestamp >= ?"
    params = [username, since]

    if status_filter != "all":
        where += " AND status = ?"
        params.append(status_filter)

    total = db.execute(
        f"SELECT count(*) FROM messages {where}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    messages = db.execute(
        f"""SELECT timestamp, status, sender, recipient, relay, delay
            FROM messages {where}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset]
    ).fetchall()

    total_pages = (total + per_page - 1) // per_page

    # Statistiche giornaliere
    daily_stats = db.execute(
        """SELECT
               date(timestamp) as day,
               count(*) as total,
               sum(case when status='delivered' then 1 else 0 end) as delivered,
               sum(case when status='bounced' then 1 else 0 end) as bounced,
               sum(case when status='deferred' then 1 else 0 end) as deferred,
               sum(case when status='dropped' then 1 else 0 end) as dropped
           FROM messages
           WHERE sasl_username = ? AND timestamp >= ?
           GROUP BY day
           ORDER BY day DESC
           LIMIT 30""",
        [username, since]
    ).fetchall()

    # Totali mese corrente
    month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d 00:00:00")
    month_stats = db.execute(
        """SELECT
               count(*) as total,
               sum(case when status='delivered' then 1 else 0 end) as delivered,
               sum(case when status='bounced' then 1 else 0 end) as bounced,
               sum(case when status='deferred' then 1 else 0 end) as deferred,
               sum(case when status='dropped' then 1 else 0 end) as dropped
           FROM messages
           WHERE sasl_username = ? AND timestamp >= ?""",
        [username, month_start]
    ).fetchone()

    return render_template("dashboard.html",
        username=username,
        messages=messages,
        daily_stats=daily_stats,
        month_stats=month_stats,
        status_filter=status_filter,
        days=days,
        page=page,
        total_pages=total_pages,
        total=total
    )


@app.route("/chart")
@login_required
def chart():
    username = session["username"]
    db = get_db()

    month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d 00:00:00")
    month_label = datetime.now().strftime("%B %Y")

    daily = db.execute(
        """SELECT
               date(timestamp) as day,
               sum(case when status='delivered' then 1 else 0 end) as delivered,
               sum(case when status='bounced'   then 1 else 0 end) as bounced,
               sum(case when status='deferred'  then 1 else 0 end) as deferred,
               sum(case when status='dropped'   then 1 else 0 end) as dropped,
               count(*) as total
           FROM messages
           WHERE sasl_username = ? AND timestamp >= ?
           GROUP BY day
           ORDER BY day ASC""",
        [username, month_start]
    ).fetchall()

    month_stats = db.execute(
        """SELECT
               count(*) as total,
               sum(case when status='delivered' then 1 else 0 end) as delivered,
               sum(case when status='bounced'   then 1 else 0 end) as bounced,
               sum(case when status='deferred'  then 1 else 0 end) as deferred,
               sum(case when status='dropped'   then 1 else 0 end) as dropped
           FROM messages
           WHERE sasl_username = ? AND timestamp >= ?""",
        [username, month_start]
    ).fetchone()

    chart_data = {
        "labels":    [row["day"]       for row in daily],
        "delivered": [row["delivered"] for row in daily],
        "bounced":   [row["bounced"]   for row in daily],
        "deferred":  [row["deferred"]  for row in daily],
        "dropped":   [row["dropped"]   for row in daily],
        "total":     [row["total"]     for row in daily],
    }

    return render_template("chart.html",
        username=username,
        chart_data=chart_data,
        month_stats=month_stats,
        month_label=month_label,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
