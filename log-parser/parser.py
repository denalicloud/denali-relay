#!/usr/bin/env python3
"""
Log parser per Postfix — Denali PRO SA
Legge /var/log/relay-postfix.log e scrive eventi su SQLite.
"""

import re
import sqlite3
import time
import logging
from datetime import datetime

LOG_FILE = "/var/log/relay-postfix.log"
DB_FILE = "/data/relay.db"
POLL_INTERVAL = 2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_id      TEXT NOT NULL,
            timestamp     TEXT,
            sasl_username TEXT,
            sender        TEXT,
            recipient     TEXT,
            status        TEXT,
            relay         TEXT,
            delay         TEXT,
            message_id    TEXT,
            updated_at    TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_ts
        ON messages (sasl_username, timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_queue_id
        ON messages (queue_id)
    """)
    conn.commit()

TS  = r'(\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})'
QID = r'([A-F0-9]{10,})'

# Cattura submission, smtps e smtpd generico
RE_SASL = re.compile(
    TS + r'.*postfix/(?:submission/|smtps/)?smtpd\[\d+\]: ' + QID +
    r': client=\S+, sasl_method=\S+, sasl_username=(\S+)'
)
RE_MSGID = re.compile(
    TS + r'.*postfix/cleanup\[\d+\]: ' + QID +
    r': message-id=<([^>]*)>'
)
RE_FROM = re.compile(
    TS + r'.*postfix/qmgr\[\d+\]: ' + QID +
    r': from=<([^>]*)>, size=\d+'
)
RE_DELIVERY = re.compile(
    TS + r'.*postfix/smtp\[\d+\]: ' + QID +
    r': to=<([^>]+)>, relay=([^,]+), delay=([^,]+).*status=(\w+)'
)
RE_REJECT = re.compile(
    TS + r'.*postfix/\S+\[\d+\]: ' + QID +
    r': reject:.*to=<([^>]+)>'
)

def parse_timestamp(ts_str):
    try:
        year = datetime.now().year
        dt = datetime.strptime(f"{year} {ts_str.strip()}", "%Y %b %d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts_str.strip()

def upsert_message(conn, queue_id, **kwargs):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = conn.execute(
        "SELECT id FROM messages WHERE queue_id = ?", (queue_id,)
    ).fetchone()

    if existing:
        updates = {k: v for k, v in kwargs.items() if v is not None}
        if updates:
            sets = ", ".join(f"{k} = ?" for k in updates)
            vals = list(updates.values())
            conn.execute(
                f"UPDATE messages SET {sets}, updated_at = ? WHERE queue_id = ?",
                vals + [now, queue_id]
            )
    else:
        kwargs['queue_id'] = queue_id
        kwargs['updated_at'] = now
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" * len(kwargs))
        conn.execute(
            f"INSERT INTO messages ({cols}) VALUES ({placeholders})",
            list(kwargs.values())
        )
    conn.commit()

def process_line(conn, line):
    m = RE_SASL.search(line)
    if m:
        ts, qid, username = m.group(1), m.group(2), m.group(3)
        upsert_message(conn, qid,
            timestamp=parse_timestamp(ts),
            sasl_username=username,
            status="accepted"
        )
        return

    m = RE_MSGID.search(line)
    if m:
        ts, qid, msgid = m.group(1), m.group(2), m.group(3)
        upsert_message(conn, qid, message_id=msgid)
        return

    m = RE_FROM.search(line)
    if m:
        ts, qid, sender = m.group(1), m.group(2), m.group(3)
        upsert_message(conn, qid, sender=sender)
        return

    m = RE_DELIVERY.search(line)
    if m:
        ts, qid, recipient, relay, delay, status = (
            m.group(1), m.group(2), m.group(3),
            m.group(4), m.group(5), m.group(6)
        )
        status_map = {
            "sent": "delivered",
            "bounced": "bounced",
            "deferred": "deferred"
        }
        upsert_message(conn, qid,
            timestamp=parse_timestamp(ts),
            recipient=recipient,
            relay=relay.strip(),
            delay=delay.strip(),
            status=status_map.get(status, status)
        )
        return

    m = RE_REJECT.search(line)
    if m:
        ts, qid, recipient = m.group(1), m.group(2), m.group(3)
        upsert_message(conn, qid,
            timestamp=parse_timestamp(ts),
            recipient=recipient,
            status="dropped"
        )
        return

def tail_log(filepath):
    with open(filepath, "r") as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if line:
                yield line
            else:
                time.sleep(POLL_INTERVAL)

def main():
    logging.info(f"Parser starting — DB: {DB_FILE}, LOG: {LOG_FILE}")
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    init_db(conn)

    logging.info("Processing historical log...")
    with open(LOG_FILE, "r") as f:
        for line in f:
            process_line(conn, line)

    count = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
    logging.info(f"Historical processing complete — {count} records in DB")

    logging.info("Tailing log for new entries...")
    for line in tail_log(LOG_FILE):
        process_line(conn, line)

if __name__ == "__main__":
    main()
