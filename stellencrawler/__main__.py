import argparse
import json
import logging
import sys

from . import __version__, config, geo, notify, store
from .sources import sh_land

log = logging.getLogger("stellencrawler")


def cmd_crawl(args, cfg):
    postings, seen = sh_land.crawl(delay=cfg["request_delay"],
                                 queries=cfg["queries"],
                                 limit_details=args.limit,
                                 user_agent=cfg["user_agent"])
    conn = store.connect(cfg["database"])
    stats = {"new": 0, "updated": 0, "unchanged": 0}
    with conn:
        for p in postings:
            stats[store.upsert(conn, p)] += 1
        # removed-Markierung nur bei kompletter Trefferliste sinnvoll
        if args.limit is None and "" in cfg["queries"]:
            removed = store.mark_removed(conn, sh_land.SOURCE, seen)
        else:
            removed = 0
    total = conn.execute("SELECT COUNT(*) c FROM postings").fetchone()["c"]
    print(f"Crawl fertig: {stats['new']} neu, {stats['updated']} aktualisiert, "
          f"{stats['unchanged']} unveraendert, {removed} entfernt. "
          f"Archiv: {total} Stellen.")

    if args.pdf:
        _export_pdfs(conn, cfg)
    if args.notify:
        notify.notify(conn, cfg, dry_run=args.dry_run)
    conn.close()


def _export_pdfs(conn, cfg):
    from . import pdf
    rows = conn.execute(
        "SELECT id, url, title FROM postings WHERE status='active'").fetchall()
    written = pdf.export_pdfs([dict(r) for r in rows], cfg["pdf_dir"],
                              user_agent=cfg["user_agent"])
    with conn:
        for pid, path in written.items():
            store.set_pdf_path(conn, pid, path)
    print(f"{len(written)} PDFs geschrieben nach {cfg['pdf_dir']}")


def cmd_pdf(args, cfg):
    conn = store.connect(cfg["database"])
    _export_pdfs(conn, cfg)
    conn.close()


def cmd_notify(args, cfg):
    conn = store.connect(cfg["database"])
    stats = notify.notify(conn, cfg, dry_run=args.dry_run)
    for email, s in stats.items():
        print(f"{email}: {s['new']} neue von {s['matched']} Treffern")
    conn.close()


def cmd_matches(args, cfg):
    """Preview: welche archivierten Stellen triggern welche Keywords –
    zum Tunen der Suchbegriffe ohne Mailversand."""
    conn = store.connect(cfg["database"])
    recs = cfg.get("recipients") or []
    if args.recipient:
        recs = [r for r in recs
                if args.recipient.lower() in (r.get("name", "") + r["email"]).lower()]
        if not recs:
            sys.exit(f"Kein Empfaenger gefunden: {args.recipient}")
    for rec in recs:
        matches = notify.recipient_matches(conn, rec)
        print(f"\n=== {rec.get('name') or rec['email']} "
              f"({len(matches)} Stellen) ===")
        for kw in rec.get("keywords") or []:
            rows = store.match_keyword(conn, kw)
            print(f"  {kw:28} -> {len(rows):4} Treffer")
        for kw in rec.get("title_keywords") or []:
            rows = store.match_keyword(conn, kw, column="title")
            print(f"  [Titel] {kw:21} -> {len(rows):4} Treffer")
        for kw in rec.get("exclude_title") or []:
            rows = store.match_keyword(conn, kw, column="title")
            print(f"  [ausschl.] {kw:15} -> {len(rows):4} ausgeschlossen")
        print("\nTrefferliste:")
        for pid, e in sorted(matches.items(), reverse=True,
                             key=lambda kv: kv[1]['row']['first_seen'])[:args.top]:
            r = e["row"]
            print(f"  {pid:20} [{r['status']:7}] {r['title'][:65]}")
            print(f"  {'':20} Keywords: {', '.join(sorted(e['keywords']))}")
            dist = geo.format_distance(e.get("distance"))
            if dist:
                print(f"  {'':20} Entfernung: {dist} "
                      f"(Luftlinie ab {rec.get('home_plz')})")
    conn.close()


def cmd_list(args, cfg):
    conn = store.connect(cfg["database"])
    rows = conn.execute(
        "SELECT id, status, title, employer, last_update, first_seen "
        "FROM postings ORDER BY first_seen DESC").fetchall()
    for r in rows:
        print(f"[{r['status']:7}] {r['id']:20} {r['title'][:70]:70} "
              f"{(r['employer'] or '')[:40]}")
    print(f"{len(rows)} Eintraege")
    conn.close()


def cmd_search(args, cfg):
    conn = store.connect(cfg["database"])
    rows = store.search(conn, args.query)
    for r in rows:
        print(f"{r['id']:20} [{r['status']:7}] {r['title']}")
        print(f"{'':20} {r['employer'] or ''} | {r['location'] or ''}")
    print(f"{len(rows)} Treffer")
    conn.close()


def cmd_show(args, cfg):
    conn = store.connect(cfg["database"])
    r = conn.execute("SELECT * FROM postings WHERE id=?", (args.id,)).fetchone()
    if not r:
        sys.exit(f"Kein Eintrag: {args.id}")
    d = dict(r)
    d["fields"] = json.loads(d.pop("fields_json") or "{}")
    for k, v in d.items():
        if k == "description_text" and v and not args.full:
            v = v[:400] + "..."
        print(f"{k}: {v}")
    hist = store.history(conn, args.id)
    if hist:
        print(f"\n--- Historie ({len(hist)} Versionen) ---")
        for h in hist:
            print(f"{h['seen_at']}  geaendert: {h['changed_fields']}")
    conn.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = config.load()
    ap = argparse.ArgumentParser(prog="stellencrawler",
                                 description="Stellenarchiv Land Schleswig-Holstein")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("crawl", help="Stellenlisten + Details abrufen und archivieren")
    p.add_argument("--pdf", action="store_true", help="neue Stellen zusaetzlich als PDF speichern")
    p.add_argument("--notify", action="store_true", help="nach dem Crawl Keyword-Mails versenden")
    p.add_argument("--dry-run", action="store_true", help="Mails nur anzeigen, nicht senden")
    p.add_argument("--limit", type=int, default=None,
                   help="nur N Detailseiten abrufen (Test)")
    p.set_defaults(fn=cmd_crawl)

    p = sub.add_parser("notify", help="Keyword-Mails an Empfaenger versenden")
    p.add_argument("--dry-run", action="store_true",
                   help="Mails nur anzeigen, nicht senden (und nichts als benachrichtigt speichern)")
    p.set_defaults(fn=cmd_notify)

    p = sub.add_parser("matches", help="zeigt, welche Stellen die Keywords der Empfaenger treffen")
    p.add_argument("--recipient", help="nur fuer diesen Empfaenger (Name/E-Mail-Teil)")
    p.add_argument("--top", type=int, default=20, help="max. Trefferlisten-Eintraege")
    p.set_defaults(fn=cmd_matches)

    p = sub.add_parser("pdf", help="fehlende PDFs fuer aktive Stellen erzeugen")
    p.set_defaults(fn=cmd_pdf)

    p = sub.add_parser("list", help="alle archivierten Stellen anzeigen")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("search", help="Volltextsuche im Archiv")
    p.add_argument("query")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("show", help="Details + Historie einer Stelle")
    p.add_argument("id")
    p.add_argument("--full", action="store_true", help="kompletten Anzeigentext")
    p.set_defaults(fn=cmd_show)

    args = ap.parse_args()
    args.fn(args, cfg)


if __name__ == "__main__":
    main()
