"""SQLite-Archiv: aktuelle Stellen, Versionshistorie, FTS5-Volltextsuche."""

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    id                TEXT PRIMARY KEY,
    source            TEXT NOT NULL,
    url               TEXT NOT NULL,
    title             TEXT,
    employer          TEXT,
    location          TEXT,
    fields_json       TEXT,
    description_html  TEXT,
    description_text  TEXT,
    contact           TEXT,
    contact_email     TEXT,
    date_posted       TEXT,
    last_update       TEXT,
    content_hash      TEXT,
    first_seen        TEXT NOT NULL,
    last_seen         TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'active',
    pdf_path          TEXT
);
CREATE TABLE IF NOT EXISTS posting_history (
    rowid            INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id       TEXT NOT NULL,
    seen_at          TEXT NOT NULL,
    content_hash     TEXT,
    changed_fields   TEXT,
    fields_json      TEXT,
    description_text TEXT,
    snapshot_json    TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS postings_fts USING fts5(
    posting_id UNINDEXED, title, employer, location, description
);
CREATE TABLE IF NOT EXISTS notifications (
    recipient        TEXT NOT NULL,
    posting_id       TEXT NOT NULL,
    sent_at          TEXT NOT NULL,
    matched_keywords TEXT,
    PRIMARY KEY (recipient, posting_id)
);
"""

SCHEMA_VERSION = 3

CONTENT_FIELDS = ("title", "employer", "location", "fields", "description_text",
                  "contact", "last_update")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    old = conn.execute("PRAGMA user_version").fetchone()[0]
    if old < 2:
        _rebuild_fts(conn)
    if old < 3:
        cols = {r[1] for r in
                conn.execute("PRAGMA table_info(posting_history)")}
        if "snapshot_json" not in cols:
            conn.execute("ALTER TABLE posting_history"
                         " ADD COLUMN snapshot_json TEXT")
    if old < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    return conn


def _rebuild_fts(conn: sqlite3.Connection):
    conn.execute("DELETE FROM postings_fts")
    for row in conn.execute("SELECT * FROM postings").fetchall():
        try:
            fields = json.loads(row["fields_json"] or "{}")
        except Exception:
            fields = {}
        _fts_replace(conn, {
            "id": row["id"], "title": row["title"],
            "employer": row["employer"], "location": row["location"],
            "description_text": row["description_text"], "fields": fields,
        })


def _normalize(p: dict) -> dict:
    return {
        "id": p["id"],
        "source": p.get("source", "sh_land"),
        "url": p["url"],
        "title": p.get("title"),
        "employer": p.get("employer"),
        "location": (p.get("fields") or {}).get("Einsatzort")
                    or (p.get("list_fields") or {}).get("Arbeitsort"),
        "fields": {**(p.get("list_fields") or {}), **(p.get("fields") or {})},
        "description_html": p.get("description_html"),
        "description_text": p.get("description_text"),
        "contact": p.get("contact"),
        "contact_email": p.get("contact_email"),
        "date_posted": p.get("date_posted"),
        "last_update": p.get("last_update"),
    }


def _hash(n: dict) -> str:
    payload = json.dumps({k: n.get(k) for k in CONTENT_FIELDS},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def upsert(conn: sqlite3.Connection, posting: dict, seen_ids: set[str] | None = None) -> str:
    """Fuegt ein Posting ein oder aktualisiert es. Rueckgabe: new|updated|unchanged."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = _normalize(posting)
    chash = _hash(n)
    row = conn.execute("SELECT * FROM postings WHERE id=?", (n["id"],)).fetchone()

    if row is None:
        conn.execute(
            """INSERT INTO postings
               (id, source, url, title, employer, location, fields_json,
                description_html, description_text, contact, contact_email,
                date_posted, last_update, content_hash, first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (n["id"], n["source"], n["url"], n["title"], n["employer"], n["location"],
             json.dumps(n["fields"], ensure_ascii=False), n["description_html"],
             n["description_text"], n["contact"], n["contact_email"],
             n["date_posted"], n["last_update"], chash, now, now),
        )
        _fts_replace(conn, n)
        return "new"

    if row["content_hash"] == chash:
        conn.execute("UPDATE postings SET last_seen=?, status='active' WHERE id=?",
                     (now, n["id"]))
        return "unchanged"

    old_fields = json.loads(row["fields_json"] or "{}")
    changed = [k for k in CONTENT_FIELDS
               if (old_fields if k == "fields" else row[k]) !=
                  (n["fields"] if k == "fields" else n.get(k))]
    snapshot = {k: (old_fields if k == "fields" else row[k])
                for k in CONTENT_FIELDS}
    conn.execute(
        """INSERT INTO posting_history
           (posting_id, seen_at, content_hash, changed_fields, fields_json,
            description_text, snapshot_json)
           VALUES (?,?,?,?,?,?,?)""",
        (n["id"], now, row["content_hash"], json.dumps(changed, ensure_ascii=False),
         row["fields_json"], row["description_text"],
         json.dumps(snapshot, ensure_ascii=False)),
    )
    conn.execute(
        """UPDATE postings SET title=?, employer=?, location=?, fields_json=?,
           description_html=?, description_text=?, contact=?, contact_email=?,
           date_posted=?, last_update=?, content_hash=?, last_seen=?, status='active'
           WHERE id=?""",
        (n["title"], n["employer"], n["location"],
         json.dumps(n["fields"], ensure_ascii=False), n["description_html"],
         n["description_text"], n["contact"], n["contact_email"],
         n["date_posted"], n["last_update"], chash, now, n["id"]),
    )
    _fts_replace(conn, n)
    return "updated"


def mark_removed(conn: sqlite3.Connection, source: str, seen_ids: set[str]) -> int:
    """Aktive Stellen der Quelle, die nicht mehr gelistet sind, als removed markieren."""
    active = conn.execute(
        "SELECT id FROM postings WHERE source=? AND status='active'", (source,)
    ).fetchall()
    gone = [r["id"] for r in active if r["id"] not in seen_ids]
    conn.executemany("UPDATE postings SET status='removed' WHERE id=?",
                     [(i,) for i in gone])
    return len(gone)


def _fts_replace(conn: sqlite3.Connection, n: dict):
    # Indexierter Text = Beschreibung + Feldwerte (Entgelt,
    # Aufgabenbereiche usw. enthalten relevante Begriffe)
    desc = " ".join([n["description_text"] or ""]
                    + [str(v) for v in (n.get("fields") or {}).values()])
    conn.execute("DELETE FROM postings_fts WHERE posting_id=?", (n["id"],))
    conn.execute(
        "INSERT INTO postings_fts (posting_id, title, employer, location, description)"
        " VALUES (?,?,?,?,?)",
        (n["id"], n["title"] or "", n["employer"] or "", n["location"] or "", desc),
    )


def match_keyword(conn: sqlite3.Connection, keyword: str,
                  column: str | None = None) -> list[sqlite3.Row]:
    """Prefix-Match eines Keywords ueber den Volltextindex.

    Mehrteilige Begriffe werden AND-verknuepft ('IT-Forensik' ->
    it* AND forensik*), jedes Token als Praefix ('informatik' trifft
    auch 'Informatiker'). Optional auf eine FTS-Spalte beschraenkbar
    (z. B. column='title' fuer Stellenart-Filter).
    """
    terms = re.findall(r"\w+", keyword.lower())
    if not terms:
        return []
    q = " AND ".join(f"{column + ':' if column else ''}{t}*" for t in terms)
    return conn.execute(
        "SELECT p.* FROM postings_fts f JOIN postings p ON p.id = f.posting_id"
        " WHERE postings_fts MATCH ? ORDER BY p.first_seen DESC",
        (q,),
    ).fetchall()


def notified_ids(conn: sqlite3.Connection, recipient: str,
                 posting_ids: set[str]) -> set[str]:
    if not posting_ids:
        return set()
    marks = ",".join("?" * len(posting_ids))
    rows = conn.execute(
        f"SELECT posting_id FROM notifications WHERE recipient=?"
        f" AND posting_id IN ({marks})",
        (recipient, *posting_ids),
    ).fetchall()
    return {r["posting_id"] for r in rows}


def record_notification(conn: sqlite3.Connection, recipient: str,
                        posting_id: str, keywords: list[str]):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT OR REPLACE INTO notifications"
        " (recipient, posting_id, sent_at, matched_keywords) VALUES (?,?,?,?)",
        (recipient, posting_id, now, json.dumps(keywords, ensure_ascii=False)),
    )


def search(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    safe = " OR ".join(f'"{w}"' for w in re.findall(r"\w+", query))
    if not safe:
        return []
    return conn.execute(
        """SELECT p.*, rank FROM postings_fts f
           JOIN postings p ON p.id = f.posting_id
           WHERE postings_fts MATCH ? ORDER BY rank LIMIT 50""",
        (safe,),
    ).fetchall()


def history(conn: sqlite3.Connection, posting_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM posting_history WHERE posting_id=? ORDER BY seen_at",
        (posting_id,),
    ).fetchall()


def set_pdf_path(conn: sqlite3.Connection, posting_id: str, path: str):
    conn.execute("UPDATE postings SET pdf_path=? WHERE id=?", (path, posting_id))
