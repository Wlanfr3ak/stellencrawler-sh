"""Crawler fuer die Stellensuche des Landes Schleswig-Holstein.

Die Ausschreibungen sind Interamt-Inserate, die das Landesportal ueber
/SiteGlobals/Functions/Interamt/Stellenausschreibung?id=interamt_<id> spiegelt.
Die Suche ist ein GET-Formular; die Hidden-Felder (u. a. callerId.HASH,
__time_token) muessen aus einem frisch geladenen Formular mitgeschickt werden.
"""

import logging
import re
import time
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE = "https://www.schleswig-holstein.de"
FORM_URL = f"{BASE}/SiteGlobals/Forms/Stellensuche/Stellensuche_Formular.html"
DETAIL_URL = f"{BASE}/SiteGlobals/Functions/Interamt/Stellenausschreibung"
SOURCE = "sh_land"
DEFAULT_UA = "stellencrawler/0.x (privates Stellenarchiv)"

RESULTS_PER_PAGE = "100"
SORT_ORDER = "DatumOeffentlichAusschreiben_dt desc"


def new_session(user_agent: str = DEFAULT_UA) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = user_agent
    return s


def _form_params(session: requests.Session) -> dict:
    """Laedt das Suchformular und liefert alle Hidden-/Textfeld-Werte."""
    html = session.get(FORM_URL, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", attrs={"name": "searchStellensuche"})
    if not form:
        raise RuntimeError("Stellensuche-Formular nicht gefunden")
    params = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if name:
            params[name] = inp.get("value", "")
    return params


def _list_pages(session: requests.Session, first_html: str) -> list[str]:
    """URLs aller Ergebnisseiten (Seite 1 ist schon geladen)."""
    soup = BeautifulSoup(first_html, "html.parser")
    pages = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # gtp-Parameter ist doppelt URL-enkodiert (..._list%253D2)
        m = re.search(r"_list=(\d+)", unquote(unquote(href)))
        if m:
            pages[int(m.group(1))] = urljoin(FORM_URL, href)
    return [pages[n] for n in sorted(pages) if n > 1]


def iter_result_html(session: requests.Session, query: str = ""):
    """Liefert nacheinander das HTML aller Ergebnisseiten."""
    params = _form_params(session)
    params.update(
        templateQueryString=query,
        resultsPerPage=RESULTS_PER_PAGE,
        sortOrder=SORT_ORDER,
    )
    resp = session.get(FORM_URL, params=params, timeout=60)
    resp.raise_for_status()
    yield resp.text
    for url in _list_pages(session, resp.text):
        page = session.get(url, timeout=60)
        page.raise_for_status()
        yield page.text


def parse_teaser(html: str) -> list[dict]:
    """Parst die Trefferliste zu Stellen-Stubs."""
    soup = BeautifulSoup(html, "html.parser")
    stubs = []
    for job in soup.select('div.c-teaser-job[data-testid="teaser-job"]'):
        title_el = job.select_one('[data-testid="teaser-job-stellenbezeichnung"]')
        employer_el = job.select_one('[data-testid="teaser-job-behoerde"]')
        link_el = job.select_one('a[data-testid="teaser-job-link"]')
        if not (title_el and link_el):
            continue
        url = link_el["href"]
        m = re.search(r"[?&]id=([^&]+)", url)
        fields = {}
        for li in job.select("ul.c-teaser-job__list li"):
            strong = li.find("strong")
            if not strong:
                continue
            label = strong.get_text(strip=True).rstrip(":")
            strong.extract()
            fields[label] = re.sub(r"\s+", " ", li.get_text(" ", strip=True))
        stubs.append(
            {
                "id": m.group(1) if m else url,
                "url": url,
                "title": title_el.get_text(" ", strip=True),
                "employer": employer_el.get_text(" ", strip=True) if employer_el else None,
                "list_fields": fields,
            }
        )
    return stubs


def parse_detail(html: str) -> dict:
    """Parst eine Detailseite: Metadaten, JSON-LD, Kontakt, Aktualisierungsdatum."""
    soup = BeautifulSoup(html, "html.parser")
    out = {"fields": {}, "description_html": None, "description_text": None,
           "date_posted": None, "last_update": None, "contact": None, "apply_url": None}

    title_el = soup.select_one('[data-testid="joboffer-stellenbezeichnung"]')
    if title_el:
        out["title"] = title_el.get_text(" ", strip=True)

    for strong in soup.select('strong[data-testid="joboffer-intro-field"]'):
        label = strong.get_text(strip=True).rstrip(":")
        val = strong.find_next_sibling("span")
        if val:
            out["fields"][label] = re.sub(r"\s+", " ", val.get_text(" ", strip=True))

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            import json
            data = json.loads(script.string or "")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            out["description_html"] = data.get("description")
            out["date_posted"] = data.get("datePosted")
            org = data.get("hiringOrganization") or {}
            out["employer"] = org.get("name")
            out["employer_url"] = org.get("sameAs")
            break
    if out["description_html"]:
        out["description_text"] = re.sub(
            r"\s+", " ", BeautifulSoup(out["description_html"], "html.parser").get_text(" ", strip=True)
        )

    contact = soup.select_one(".c-contact-box-embedded")
    if contact:
        out["contact"] = re.sub(r"\s+", " ", contact.get_text(" ", strip=True))
        mail = contact.find("a", href=re.compile(r"^mailto:", re.I))
        if mail:
            out["contact_email"] = mail["href"][7:]

    m = re.search(r"Letzte Aktualisierung am:\s*([\d.]+)", html)
    if m:
        out["last_update"] = m.group(1)
    return out


def crawl(delay: float = 0.4, queries: list[str] | None = None,
          limit_details: int | None = None, user_agent: str = DEFAULT_UA):
    """Kompletter Lauf: Trefferlisten + Detailseiten.

    Liefert (postings, seen_ids): postings = Liste vollstaendiger Dicts,
    seen_ids = alle in den Listen gefundenen IDs (auch ohne Detailabruf).
    """
    session = new_session(user_agent)
    queries = queries if queries is not None else [""]
    stubs, seen = {}, set()
    for q in queries:
        for page_html in iter_result_html(session, q):
            for stub in parse_teaser(page_html):
                seen.add(stub["id"])
                stubs.setdefault(stub["id"], stub)
    log.info("%d Stellen in Trefferlisten gefunden", len(stubs))

    postings, n = [], 0
    for stub in stubs.values():
        if limit_details is not None and n >= limit_details:
            break
        try:
            resp = session.get(stub["url"], timeout=60)
            resp.raise_for_status()
            detail = parse_detail(resp.text)
        except Exception:
            log.exception("Detailabruf fehlgeschlagen: %s", stub["url"])
            detail = {}
        postings.append({**stub, **detail, "source": SOURCE})
        n += 1
        time.sleep(delay)
    return postings, seen
