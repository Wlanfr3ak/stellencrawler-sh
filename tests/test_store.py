"""SQLite-Archiv: Upsert-Logik, Historie, FTS, Removed-Markierung,
Notifications."""

import json

from stellencrawler import store
from conftest import make_posting


def test_upsert_new(conn):
    assert store.upsert(conn, make_posting()) == "new"
    row = conn.execute("SELECT * FROM postings WHERE id='interamt_1'").fetchone()
    assert row["status"] == "active"
    assert row["title"] == "Fachinformatiker (m/w/d)"
    assert json.loads(row["fields_json"])["Entgelt"] == "TV-L E 10"
    assert row["first_seen"] == row["last_seen"]


def test_upsert_unchanged(conn):
    store.upsert(conn, make_posting())
    assert store.upsert(conn, make_posting()) == "unchanged"
    assert conn.execute("SELECT COUNT(*) c FROM posting_history").fetchone()["c"] == 0


def test_upsert_updated_writes_history(conn):
    store.upsert(conn, make_posting())
    changed = make_posting(title="Fachinformatikerin (m/w/d)",
                           fields={"Entgelt": "TV-L E 11"})
    assert store.upsert(conn, changed) == "updated"
    hist = conn.execute("SELECT * FROM posting_history").fetchall()
    assert len(hist) == 1
    changed_fields = json.loads(hist[0]["changed_fields"])
    assert "title" in changed_fields and "fields" in changed_fields
    # alter Gesamtstand liegt als Snapshot in der Historie
    snap = json.loads(hist[0]["snapshot_json"])
    assert snap["title"] == "Fachinformatiker (m/w/d)"
    assert snap["fields"]["Entgelt"] == "TV-L E 10"


def test_fts_updated_on_change(conn):
    store.upsert(conn, make_posting(title="Techniker",
                 description_text="Informatik gesucht"))
    assert store.match_keyword(conn, "Informatik")
    store.upsert(conn, make_posting(title="Techniker",
                 description_text="Nur noch Tiefbau"))
    assert not store.match_keyword(conn, "informatik")


def test_mark_removed(conn):
    store.upsert(conn, make_posting("a"))
    store.upsert(conn, make_posting("b"))
    assert store.mark_removed(conn, "sh_land", {"a"}) == 1
    status = {r["id"]: r["status"] for r in
              conn.execute("SELECT id,status FROM postings")}
    assert status == {"a": "active", "b": "removed"}


def test_removed_posting_reappears_active(conn):
    store.upsert(conn, make_posting("a"))
    store.mark_removed(conn, "sh_land", set())
    assert store.upsert(conn, make_posting("a")) == "unchanged"
    row = conn.execute("SELECT status FROM postings WHERE id='a'").fetchone()
    assert row["status"] == "active"


def test_match_keyword_prefix_and_and(conn):
    store.upsert(conn, make_posting("a",
                 description_text="Informatikerin gesucht, IT-Forensik"))
    store.upsert(conn, make_posting("b", title="Maurer",
                 description_text="Bauarbeiten", fields={}))
    assert {r["id"] for r in store.match_keyword(conn, "informatik")} == {"a"}
    # Praefix: 'informatik' trifft 'Informatikerin'
    assert store.match_keyword(conn, "informatik")[0]["id"] == "a"
    # AND-Verknuepfung mehrteiliger Begriffe
    assert store.match_keyword(conn, "it forensik")
    assert not store.match_keyword(conn, "it forensik bau")


def test_match_keyword_column_title(conn):
    # 'Ausbildung' steht nur im Text, nicht im Titel
    store.upsert(conn, make_posting(title="Techniker",
                 description_text="Voraussetzung: abgeschlossene Ausbildung"))
    assert store.match_keyword(conn, "ausbildung")            # Volltext trifft
    assert not store.match_keyword(conn, "ausbildung", column="title")
    store.upsert(conn, make_posting(
        "b", title="Auszubildende Fachinformatikerin", description_text="x"))
    assert {r["id"] for r in
            store.match_keyword(conn, "ausbildung", column="title")} == set()
    assert {r["id"] for r in
            store.match_keyword(conn, "auszubildende", column="title")} == {"b"}


def test_match_keyword_searches_field_values(conn):
    store.upsert(conn, make_posting(
        "a", description_text="x",
        fields={"Aufgabenbereiche": "Bau und Architektur"}))
    assert store.match_keyword(conn, "architektur")


def test_search(conn):
    store.upsert(conn, make_posting(title="Bauingenieur Hochbau"))
    rows = store.search(conn, "bauingenieur")
    assert rows and rows[0]["id"] == "interamt_1"


def test_notifications_roundtrip(conn):
    store.upsert(conn, make_posting("a"))
    store.upsert(conn, make_posting("b"))
    assert store.notified_ids(conn, "x@y", {"a", "b"}) == set()
    store.record_notification(conn, "x@y", "a", ["informatik"])
    assert store.notified_ids(conn, "x@y", {"a", "b"}) == {"a"}
    # anderer Empfaenger ist unabhaengig
    assert store.notified_ids(conn, "z@y", {"a"}) == set()


def test_set_pdf_path(conn):
    store.upsert(conn, make_posting())
    store.set_pdf_path(conn, "interamt_1", "archive/pdf/interamt_1.pdf")
    row = conn.execute("SELECT pdf_path FROM postings").fetchone()
    assert row["pdf_path"].endswith("interamt_1.pdf")


def test_schema_migration_rebuilds_fts(conn):
    store.upsert(conn, make_posting())
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 2
    assert conn.execute("SELECT COUNT(*) c FROM postings_fts").fetchone()["c"] == 1
