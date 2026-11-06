import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_html():
    def _read(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")
    return _read


@pytest.fixture
def conn(tmp_path):
    from stellencrawler import store
    c = store.connect(tmp_path / "jobs.db")
    yield c
    c.close()


def make_posting(pid="interamt_1", **kw):
    p = {
        "id": pid,
        "source": "sh_land",
        "url": f"https://example.test/{pid}",
        "title": "Fachinformatiker (m/w/d)",
        "employer": "Testbehörde",
        "location": "Kiel",
        "fields": {"Entgelt": "TV-L E 10", "Wochenarbeitszeit TB.": "38.7",
                   "Einsatzort": "Musterstraße 1, 24103 Kiel"},
        "description_text": "Wir suchen Verstärkung in der Informatik. "
                            "Mobiles Arbeiten ist möglich.",
        "description_html": "<p>Beschreibung</p>",
        "contact": "Testbehörde Kiel",
        "contact_email": "a@b.de",
        "date_posted": "2026-01-01",
        "last_update": "01.01.2026",
    }
    p.update(kw)
    return p


@pytest.fixture
def portal(fixture_html, monkeypatch):
    """Lokaler HTTP-Server, der das SH-Portal mit echten Fixture-HTMLs
    nachbildet (kein Live-Traffic in Tests)."""
    from stellencrawler.sources import sh_land

    form = fixture_html("form.html")
    results = fixture_html("results2.html")
    detail = fixture_html("detail.html")

    class Handler(BaseHTTPRequestHandler):
        def _page(self) -> str:
            if "Stellenausschreibung" in self.path:
                return detail
            q = urlparse(self.path).query
            if "templateQueryString" in q or "gtp" in q:
                return results.replace(
                    "https://www.schleswig-holstein.de",
                    self.server.base_local)
            return form

        def do_GET(self):
            body = self._page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.base_local = f"http://127.0.0.1:{httpd.server_port}"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(sh_land, "FORM_URL",
                        f"{httpd.base_local}/Stellensuche_Formular")
    yield httpd.base_local
    httpd.shutdown()
