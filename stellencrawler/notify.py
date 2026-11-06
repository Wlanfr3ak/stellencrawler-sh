"""Keyword-Matching + E-Mail-Benachrichtigung pro Empfaenger.

Matching laeuft lokal ueber den FTS5-Volltextindex (Titel, Behoerde, Ort,
Feldwerte, kompletter Anzeigentext) – unabhaengig von den Suchformularen
der Portale und deren wechselnden Begrifflichkeiten.
"""

import html as html_mod
import json
import logging
import re
import smtplib
import sqlite3
from email.message import EmailMessage

from . import geo, store

log = logging.getLogger(__name__)

# Erkennt Angebote von mobilem/Hybrid-Arbeiten im Anzeigentext
_MOBILE_RE = re.compile(
    r"mobil\w*\s+arbeit|home[\s-]*office|telearbeit|hybrid|remote|"
    r"ortsflexib|ortsunabh",
    re.I,
)


def _pick(fields: dict, *substrs: str) -> str | None:
    """Ersten Feldwert liefern, dessen Schluessel eines der Woerter enthaelt."""
    for k, v in fields.items():
        if any(s.lower() in k.lower() for s in substrs):
            return str(v)
    return None


def recipient_matches(conn: sqlite3.Connection, recipient: dict) -> dict:
    """{posting_id: {'row': Row, 'keywords': {kw}, 'distance': km|None}}.

    'keywords' matchen ueber den Volltext, 'title_keywords' zusaetzlich
    nur ueber den Titel (beides OR) – Titel-only fuer Begriffe, die im
    Fliesstext rauschen (z. B. 'EDV-Kenntnisse', 'Netzwerk aufbauen').
    'exclude_title' ist ein Negativ-Filter auf den Titel (z. B. weil
    'Ausbildung' im Volltext fast ueberall als Anforderung vorkommt).
    'distance' enthaelt die grobe Luftlinien-Entfernung ab
    'home_plz' (geo.py) – zur Anzeige in matches/Mail.
    """
    matches = {}
    for kw in recipient.get("keywords") or []:
        for row in store.match_keyword(conn, kw):
            entry = matches.setdefault(row["id"], {"row": row, "keywords": set()})
            entry["keywords"].add(kw)
    for kw in recipient.get("title_keywords") or []:
        for row in store.match_keyword(conn, kw, column="title"):
            entry = matches.setdefault(row["id"], {"row": row, "keywords": set()})
            entry["keywords"].add(kw)
    excl = [t for t in (recipient.get("exclude_title") or []) if t]
    for kw in excl:
        for row in store.match_keyword(conn, kw, column="title"):
            matches.pop(row["id"], None)
    home = recipient.get("home_plz")
    if home:
        for e in matches.values():
            e["distance"] = geo.distance_of(e["row"], home)
    return matches


def _job_cells(row: sqlite3.Row) -> dict:
    try:
        fields = json.loads(row["fields_json"] or "{}")
    except Exception:
        fields = {}
    searchable = (row["description_text"] or "") + " " + " ".join(
        str(v) for v in fields.values())
    return {
        "hours": _pick(fields, "wochenarbeitszeit")
                 or _pick(fields, "teilzeit") or "–",
        "pay": _pick(fields, "entgelt", "besoldung") or "–",
        "place": _pick(fields, "einsatzort", "arbeitsort")
                 or row["location"] or "–",
        "mobile": "ja" if _MOBILE_RE.search(searchable) else "–",
        "fields": fields,
    }


def build_mail(recipient: dict, hits: list[dict],
               smtp_from: str = "stellencrawler@localhost") -> EmailMessage:
    name = recipient.get("name") or recipient["email"]
    msg = EmailMessage()
    msg["Subject"] = f"Stellencrawler: {len(hits)} neue Stellenangebote"
    msg["From"] = smtp_from
    msg["To"] = recipient["email"]

    # --- Plain-Text-Fallback (kompakt) ---
    lines = [f"Hallo {name},", "",
             f"{len(hits)} neue Stelle(n) passen zu deinen Suchbegriffen:", ""]
    for h in hits:
        r = h["row"]
        c = _job_cells(r)
        dist = geo.format_distance(h.get("distance"))
        lines += [f"* {r['title']} ({c['pay']}, {c['hours']}, {c['place']})"]
        if dist:
            lines.append(f"  {dist} Luftlinie")
        lines.append(f"  {r['url']}")
    lines += ["--", "stellencrawler"]
    msg.set_content("\n".join(lines))

    # --- HTML-Tabelle ---
    e = html_mod.escape
    rows_html = ""
    for h in hits:
        r = h["row"]
        c = _job_cells(r)
        kws = e(", ".join(sorted(h["keywords"])))
        dist = geo.format_distance(h.get("distance"))
        dist_html = (f"<br>📍 {e(dist)} Luftlinie" if dist else "")
        rows_html += (
            "<tr>"
            f"<td><b>{e(r['title'] or '')}</b><br>"
            f"<small>{e(r['employer'] or '')}<br>Treffer: {kws}"
            f"{dist_html}</small></td>"
            f"<td>{e(c['hours'])}</td>"
            f"<td>{e(c['pay'])}</td>"
            f"<td>{e(c['place'])}</td>"
            f"<td style='text-align:center'>{c['mobile']}</td>"
            f"<td><a href='{e(r['url'])}'>zur Stelle</a></td>"
            "</tr>"
        )
    html_body = f"""<html><body style="font-family:sans-serif;font-size:14px">
<p>Hallo {e(name)},</p>
<p>{len(hits)} neue Stelle(n) passen zu deinen Suchbegriffen:</p>
<table border="1" cellspacing="0" cellpadding="6"
       style="border-collapse:collapse;border-color:#ccc">
<thead><tr style="background:#011E4A;color:#fff">
<th style="text-align:left">Stelle</th><th>Std./Woche</th><th>Entgelt</th>
<th>Arbeitsort</th><th>Mobil?</th><th>Link</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
<p style="color:#888"><small>– stellencrawler</small></p>
</body></html>"""
    msg.add_alternative(html_body, subtype="html")
    return msg


def send_mail(smtp_cfg: dict, msg: EmailMessage):
    port = int(smtp_cfg.get("port", 587))
    if port == 465:
        smtp = smtplib.SMTP_SSL(smtp_cfg["host"], port, timeout=30)
    else:
        smtp = smtplib.SMTP(smtp_cfg["host"], port, timeout=30)
        smtp.starttls()
    if smtp_cfg.get("user"):
        smtp.login(smtp_cfg["user"], smtp_cfg.get("password") or "")
    smtp.send_message(msg)
    smtp.quit()


def notify(conn: sqlite3.Connection, cfg: dict, dry_run: bool = False) -> dict:
    """Prueft alle Empfaenger auf neue Keyword-Treffer und benachrichtigt."""
    smtp_cfg = cfg.get("smtp") or {}
    stats = {}
    for rec in cfg.get("recipients") or []:
        matches = recipient_matches(conn, rec)
        new_ids = set(matches) - store.notified_ids(conn, rec["email"], set(matches))
        stats[rec["email"]] = {"matched": len(matches), "new": len(new_ids)}
        if not new_ids:
            log.info("%s: %d Treffer, keine neuen", rec["email"], len(matches))
            continue
        hits = [matches[i] for i in sorted(
            new_ids, key=lambda i: matches[i]["row"]["first_seen"], reverse=True)]
        msg = build_mail(rec, hits, smtp_cfg.get("from", "stellencrawler@localhost"))
        if dry_run:
            print(f"===== DRY-RUN Mail an {rec['email']} =====")
            print(msg.as_string()[:3000])
        else:
            if not smtp_cfg.get("host"):
                log.error("smtp.host nicht konfiguriert (config.yaml) – "
                          "Mail an %s nicht gesendet", rec["email"])
                continue
            send_mail(smtp_cfg, msg)
            log.info("%s: %d neue Treffer gesendet", rec["email"], len(hits))
            with conn:
                for h in hits:
                    store.record_notification(conn, rec["email"],
                                              h["row"]["id"],
                                              sorted(h["keywords"]))
    return stats
