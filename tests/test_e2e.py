"""End-to-End: kompletter Crawl-Zyklus gegen lokalen Fixture-Server –
Trefferliste -> Detailseiten -> Archiv -> Matching -> Mail.
Kein Live-Traffic."""

from collections import Counter

from stellencrawler import notify, store
from stellencrawler.sources import sh_land


def test_full_cycle(portal, conn):
    postings, seen = sh_land.crawl(delay=0, queries=[""])
    assert len(postings) >= 10
    assert len(seen) >= len(postings)
    assert all(p["id"].startswith("interamt_") for p in postings)

    # Detaildaten kamen an
    p0 = postings[0]
    assert p0["title"] and p0["description_text"]

    stats = Counter(store.upsert(conn, p) for p in postings)
    conn.commit()
    assert stats["new"] == len(postings)

    # Matching + Mail-Flow
    rows = store.match_keyword(conn, "ingenieur")
    assert rows
    rec = {"name": "E2E", "email": "e2e@test",
           "keywords": ["ingenieur", "techniker"]}
    matches = notify.recipient_matches(conn, rec)
    assert matches

    stats = notify.notify(conn, {"recipients": [rec], "smtp": {}},
                          dry_run=True)
    assert stats["e2e@test"]["new"] == len(matches)

    # Removed-Markierung: nur noch die Haelfte sichtbar
    keep = set(list(seen)[: len(seen) // 2])
    removed = store.mark_removed(conn, sh_land.SOURCE, keep)
    assert removed == len(seen) - len(keep)


def test_second_crawl_no_duplicates(portal, conn):
    postings, seen = sh_land.crawl(delay=0, queries=[""])
    for p in postings:
        store.upsert(conn, p)
    conn.commit()

    postings2, _ = sh_land.crawl(delay=0, queries=[""])
    stats = Counter(store.upsert(conn, p) for p in postings2)
    assert stats["new"] == 0
    assert stats["unchanged"] == len(postings2)
