"""PDF-Archivierung der Detailseiten via Playwright (Headless Chromium,
Print-CSS der Seite – entspricht der 'Seite drucken'-Funktion)."""

import logging
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)

WAIT_MS = 1500

# Server-Fehlerseiten (z. B. Varnish "Error 503 Backend fetch failed"
# bei Drosselung) – solche Seiten duerfen NICHT ins PDF-Archiv.
_ERR_PAGE_RE = re.compile(
    r"fetch failed|error\s*\d{3}|service unavailable|bad gateway|"
    r"not found|fehler\s*\d{3}", re.I)


def _page_failed(page) -> str | None:
    """Fehler-Grund, wenn die geladene Seite eine Server-Fehlerseite ist."""
    try:
        head = (page.title() + " " +
                page.locator("body").inner_text(timeout=3000))[:2000]
    except Exception:
        return "Seite nicht lesbar"
    m = _ERR_PAGE_RE.search(head)
    return m.group(0) if m else None


def _dismiss_cookie_banner(page):
    """Cookie-Consent wegklicken – sonst liegt eine Abdunklung ueber der
    Seite und das PDF wirkt ausgebleicht."""
    try:
        page.get_by_role("button", name="Alle auswählen").click(timeout=2500)
        page.wait_for_timeout(500)
    except Exception:
        page.evaluate("""() => {
            document.querySelector('#cookiebanner')?.remove();
            document.body.classList.remove('banner-visible');
        }""")


def export_pdfs(items: list[dict], pdf_dir: Path, delay: float = 0.5,
                user_agent: str | None = None) -> dict:
    """Speichert jede Detailseite als PDF. items: [{id,url,title}].

    Existierende PDFs werden uebersprungen. Rueckgabe: {id: pfad}.
    """
    from playwright.sync_api import sync_playwright

    pdf_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    todo = [i for i in items if not (pdf_dir / f"{i['id']}.pdf").exists()]
    log.info("PDF-Export: %d neu, %d vorhanden", len(todo), len(items) - len(todo))
    if not todo:
        return written

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(user_agent=user_agent) if user_agent else browser.new_context()
        page = ctx.new_page()
        for item in todo:
            path = pdf_dir / f"{item['id']}.pdf"
            try:
                # "load" statt "networkidle": die Seite haelt teils
                # Verbindungen offen, networkidle timed sonst aus
                page.goto(item["url"], wait_until="load", timeout=60000)
                failed = _page_failed(page)
                if failed:
                    # Fehlerseite nicht archivieren – beim naechsten
                    # Lauf fehlt die Datei und wird erneut versucht
                    log.warning("Server-Fehlerseite (%s) bei %s – "
                                "uebersprungen", failed, item["url"])
                    continue
                _dismiss_cookie_banner(page)
                page.wait_for_timeout(WAIT_MS)
                page.pdf(path=str(path), format="A4", print_background=True)
                written[item["id"]] = str(path)
            except Exception:
                log.exception("PDF fehlgeschlagen: %s", item["url"])
            time.sleep(delay)
        browser.close()
    return written
