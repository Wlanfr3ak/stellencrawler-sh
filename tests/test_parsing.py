"""Parsing der Portal-HTMLs (Formular, Trefferliste, Detailseite)."""

import re

from stellencrawler.sources import sh_land


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeSession:
    def __init__(self, text):
        self._text = text
        self.headers = {}

    def get(self, *a, **kw):
        return _FakeResp(self._text)


def test_form_params_extracts_signed_fields(fixture_html):
    params = sh_land._form_params(_FakeSession(fixture_html("form.html")))
    for key in ("resourceId", "input_", "pageLocale", "__time_token",
                "callerId", "callerId.HASH", "templateQueryString"):
        assert key in params, key
    assert params["callerId.HASH"]
    assert params["__time_token"]


def test_parse_teaser_finds_jobs(fixture_html):
    stubs = sh_land.parse_teaser(fixture_html("results2.html"))
    assert len(stubs) >= 10
    s = stubs[0]
    assert s["id"].startswith("interamt_")
    assert "Stellenausschreibung" in s["url"]
    assert s["title"]
    assert s["employer"]
    assert "Arbeitsort" in s["list_fields"]
    # alle Stubs einzigartig
    assert len({x["id"] for x in stubs}) == len(stubs)


def test_parse_teaser_fields_look_reasonable(fixture_html):
    stubs = sh_land.parse_teaser(fixture_html("results2.html"))
    labels = set()
    for s in stubs:
        labels.update(s["list_fields"])
    assert "Entgelt" in labels or "Besoldung" in labels
    assert "Bewerbungsfrist" in labels


def test_list_pages_finds_pagination(fixture_html):
    pages = sh_land._list_pages(None, fixture_html("results2.html"))
    assert len(pages) >= 1
    assert all("_list" in u for u in pages)


def test_parse_detail_extracts_everything(fixture_html):
    d = sh_land.parse_detail(fixture_html("detail.html"))
    assert "Ingenieur" in d["title"]
    assert d["fields"]["Bewerbungsfrist"] == "baldmöglichst"
    assert d["fields"]["Entgelt"] == "TV-L E 9b - TV-L E 12"
    assert "Aufgaben" in d["description_text"]
    assert len(d["description_text"]) > 300
    assert "Flensburg" in d["fields"]["Einsatzort"]
    assert "GMSH" in (d["employer"] or d["contact"])
    if d["contact_email"]:
        assert "@" in d["contact_email"]
    assert d["date_posted"] == "2023-08-24"
    assert d["last_update"] == "13.04.2026"


def test_parse_detail_tolerates_missing_parts():
    d = sh_land.parse_detail("<html><body>leer</body></html>")
    assert d["fields"] == {}
    assert d["description_text"] is None


class _FakePage:
    """Minimaler Playwright-Page-Ersatz fuer _page_failed."""
    def __init__(self, title, body):
        self._title, self._body = title, body
    def title(self):
        return self._title
    class _Loc:
        def __init__(self, text): self._t = text
        def inner_text(self, timeout=0): return self._t
    def locator(self, _sel):
        return _FakePage._Loc(self._body)


def test_page_failed_detects_server_error():
    from stellencrawler import pdf
    p = _FakePage("Error 503 Backend fetch failed",
                  "Error 503 Backend fetch failed Guru Meditation")
    assert pdf._page_failed(p) is not None


def test_page_failed_normal_posting():
    from stellencrawler import pdf
    p = _FakePage("Stellenausschreibung", "Fachinformatiker Bewerbungsfrist")
    assert pdf._page_failed(p) is None
