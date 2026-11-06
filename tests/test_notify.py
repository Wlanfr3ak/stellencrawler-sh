"""Keyword-Matching, Mail-Aufbau (HTML-Tabelle), Versand, Dedupe."""

import json

import pytest

from stellencrawler import notify, store
from conftest import make_posting


@pytest.fixture
def conn2(conn):
    store.upsert(conn, make_posting("a",
                 description_text="Informatik und mobiles Arbeiten"))
    store.upsert(conn, make_posting("b", title="Bauleiter",
                 description_text="Straßenbau", fields={}))
    conn.commit()
    return conn


REC = {"name": "Test", "email": "t@example.org",
       "keywords": ["Informatik", "Netzwerk"]}


def test_recipient_matches(conn2):
    m = notify.recipient_matches(conn2, REC)
    assert set(m) == {"a"}
    assert m["a"]["keywords"] == {"Informatik"}


def test_recipient_matches_exclude_title(conn2):
    rec = {**REC, "exclude_title": ["Ausbildung", "Auszubildende",
                                    "Werkstudent", "Duales Studium"]}
    # 'a' bleibt Treffer (Titel enthaelt keinen Ausschlussbegriff)
    assert set(notify.recipient_matches(conn2, rec)) == {"a"}
    # Ausbildungs-Stelle mit Keyword-Treffer wird ausgeschlossen
    store.upsert(conn2, make_posting("c",
                 title="Auszubildende Fachinformatikerin",
                 description_text="Informatik"))
    conn2.commit()
    assert set(notify.recipient_matches(conn2, rec)) == {"a"}
    # Ausschluss greift nur auf den Titel: 'Ausbildung' im Fließtext
    # (als Anforderung) schliesst die Stelle NICHT aus
    store.upsert(conn2, make_posting("d",
                 title="Systemadministrator Informatik",
                 description_text="Voraussetzung: abgeschlossene Ausbildung"))
    conn2.commit()
    assert set(notify.recipient_matches(conn2, rec)) == {"a", "d"}


def test_recipient_matches_title_keywords(conn2):
    # 'b': EDV steht nur im Fliesstext -> ohne title_keywords kein Treffer;
    # 'c': EDV im Titel -> trifft
    rec = {**REC, "keywords": [], "title_keywords": ["EDV"]}
    store.upsert(conn2, make_posting("b", title="Sachbearbeiter",
                 description_text="gute EDV-Kenntnisse"))
    store.upsert(conn2, make_posting("c", title="EDV-Betreuer",
                 description_text="Support"))
    conn2.commit()
    assert set(notify.recipient_matches(conn2, rec)) == {"c"}


def test_recipient_matches_distance(conn2, monkeypatch):
    import types
    from stellencrawler import geo
    fake = types.SimpleNamespace(
        query_postal_code=lambda p: types.SimpleNamespace(
            latitude=54.32, longitude=10.17))
    monkeypatch.setattr(geo, "_RES", fake)
    rec = {**REC, "home_plz": "24147"}
    m = notify.recipient_matches(conn2, rec)
    # 'a' hat in conftest location 'Harmsstr., 24114 Kiel' -> aufloesbar
    assert m["a"]["distance"] is not None
    assert m["a"]["distance"] < 5


def test_recipient_matches_no_keywords(conn2):
    assert notify.recipient_matches(conn2, {"email": "x"}) == {}


def test_job_cells_values(conn2):
    row = conn2.execute("SELECT * FROM postings WHERE id='a'").fetchone()
    c = notify._job_cells(row)
    assert c["hours"] == "38.7"
    assert c["pay"] == "TV-L E 10"
    assert "Kiel" in c["place"]
    assert c["mobile"] == "ja"


def test_job_cells_mobile_negative(conn2):
    row = conn2.execute("SELECT * FROM postings WHERE id='b'").fetchone()
    assert notify._job_cells(row)["mobile"] == "–"


def test_mobile_detection_variants():
    assert notify._MOBILE_RE.search("Telearbeit möglich")
    assert notify._MOBILE_RE.search("Home-Office")
    assert notify._MOBILE_RE.search("hybrides Arbeiten")
    assert notify._MOBILE_RE.search("mobilen Arbeiten")
    assert not notify._MOBILE_RE.search("Dienstort Kiel")


def test_build_mail_has_html_table(conn2):
    row = conn2.execute("SELECT * FROM postings WHERE id='a'").fetchone()
    hits = [{"row": row, "keywords": {"Informatik"}}]
    msg = notify.build_mail(REC, hits, "bot@x.de")
    assert msg["Subject"].startswith("Stellencrawler: 1")
    assert msg["To"] == "t@example.org"
    assert msg["From"] == "bot@x.de"
    parts = {p.get_content_type(): p.get_content()
             for p in msg.walk() if p.get_content_type().startswith("text/")}
    assert "<table" in parts["text/html"]
    assert "zur Stelle" in parts["text/html"]
    assert "Fachinformatiker" in parts["text/html"]
    assert "TV-L E 10" in parts["text/html"]
    assert "https://example.test/a" in parts["text/plain"]


def test_build_mail_escapes_html(conn2):
    store.upsert(conn2, make_posting("x", title='<b>"Hack"</b>'))
    conn2.commit()
    row = conn2.execute("SELECT * FROM postings WHERE id='x'").fetchone()
    msg = notify.build_mail(REC, [{"row": row, "keywords": set()}])
    html = [p.get_content() for p in msg.walk()
            if p.get_content_type() == "text/html"][0]
    assert "&lt;b&gt;" in html


def test_notify_dry_run_records_nothing(conn2):
    cfg = {"recipients": [REC], "smtp": {}}
    stats = notify.notify(conn2, cfg, dry_run=True)
    assert stats["t@example.org"] == {"matched": 1, "new": 1}
    assert conn2.execute("SELECT COUNT(*) c FROM notifications").fetchone()["c"] == 0


def test_notify_sends_and_dedupes(conn2, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_mail",
                        lambda smtp, msg: sent.append(msg))
    cfg = {"recipients": [REC],
           "smtp": {"host": "smtp.example.org"}}
    notify.notify(conn2, cfg)
    assert len(sent) == 1
    assert store.notified_ids(conn2, "t@example.org", {"a"}) == {"a"}
    # zweiter Lauf: nichts Neues
    stats = notify.notify(conn2, cfg)
    assert stats["t@example.org"]["new"] == 0
    assert len(sent) == 1


def test_notify_without_smtp_host_errors(conn2, caplog):
    cfg = {"recipients": [REC], "smtp": {}}
    import logging
    with caplog.at_level(logging.ERROR):
        notify.notify(conn2, cfg)
    assert "smtp.host" in caplog.text


def test_send_mail_starttls(monkeypatch):
    calls = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls["init"] = (host, port)
        def starttls(self): calls["starttls"] = True
        def login(self, u, p): calls["login"] = (u, p)
        def send_message(self, m): calls["msg"] = m
        def quit(self): calls["quit"] = True

    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    notify.send_mail({"host": "h", "port": 587, "user": "u",
                      "password": "p"}, "msg")
    assert calls["init"] == ("h", 587)
    assert calls["starttls"] and calls["login"] == ("u", "p")


def test_send_mail_ssl_port(monkeypatch):
    used = {"ssl": False}

    class FakeSSL:
        def __init__(self, h, p, timeout=None): used["ssl"] = True
        def send_message(self, m): pass
        def quit(self): pass

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSSL)
    notify.send_mail({"host": "h", "port": 465}, "msg")
    assert used["ssl"]
