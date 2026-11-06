# Stellencrawler Schleswig-Holstein

Python-Tool, das regelmäßig die Stellenangebote des Landes
Schleswig-Holstein crawlt, sie in einem durchsuchbaren Archiv mit
Update-Historie speichert und (perspektivisch) bei neuen Stellen bzw.
Keyword-Treffern Benachrichtigungs-E-Mails versendet.

**Datenquellen:**

- Landesportal SH: <https://www.schleswig-holstein.de/SiteGlobals/Forms/Stellensuche/Stellensuche_Formular.html> ✅ implementiert
- Interamt.de: <https://www.interamt.de/> ⏳ geplant

Hinweis: Die Landes-Stellen sind Interamt-Inserate
(`interamt_<id>`-IDs), die das Portal nur spiegelt – beide Quellen
teilen denselben ID-Raum und deduplizieren sich automatisch.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m playwright install chromium   # nur für PDF-Export nötig
# Entwicklung/Tests:
pip install -r requirements-dev.txt
```

## Tests

```bash
python -m pytest tests/     # 47 Tests: Parsing, Store, Config, Geo, Mail, E2E
```

Die Suite testet quer durch alle Ebenen inkl. End-to-End-Lauf gegen
einen lokalen Fixture-Server mit echtem Portal-HTML (`tests/fixtures/`) –
kein Live-Traffic nötig.

Optional `config.example.yaml` als `config.yaml` kopieren und anpassen
(lokal, gitignoriert). Wichtigste Schlüssel:

| Schlüssel | Bedeutung |
|-----------|-----------|
| `user_agent` | Identifikation des Crawlers inkl. **Kontakt-E-Mail** – wird bei allen Requests und im PDF-Browser gesendet. Bitte eigene Adresse eintragen! |
| `request_delay` | Pause zwischen Detail-Abrufen (Sekunden) |
| `queries` | Suchbegriffe für die Trefferliste (`""` = alle Stellen) |
| `recipients` | **Pro Person**: `name`, `email`, `keywords` (Volltext), optional `title_keywords` (nur Titel – für Begriffe, die im Fließtext rauschen wie „EDV-Kenntnisse"), `exclude_title` (Negativ-Filter auf Titel, z. B. Ausbildung/Duales Studium/Werkstudent), `home_plz` (grobe Luftlinien-Entfernung je Stelle in `matches`/Mail). Logik: `(keywords ODER title_keywords) UND NICHT exclude_title`. Mit `matches` testen. |
| `database`, `pdf_dir` | Ablagepfade |
| `smtp` | Mailversand: `host`, `port` (587=STARTTLS, 465=SSL), `user`, `password`, `from` |
| `version` | Versionsnummer – parallel zur `VERSION`-Datei mitzählen |

`config.yaml` enthält alle Einstellungen inkl. SMTP-Zugang – sie ist
gitignoriert, Credentials bleiben lokal.

## Nutzung

```bash
python -m stellencrawler crawl           # kompletter Bestand -> Archiv
python -m stellencrawler crawl --pdf     # + PDF je Stelle nach archive/pdf/
python -m stellencrawler crawl --limit 5 # Testlauf mit wenigen Details
python -m stellencrawler pdf             # fehlende PDFs nachholen
python -m stellencrawler list            # alle archivierten Stellen
python -m stellencrawler search "Bau"    # Volltextsuche im Archiv
python -m stellencrawler show interamt_1509617 --full

python -m stellencrawler matches         # Keyword-Treffer pro Empfänger (Preview)
python -m stellencrawler matches --recipient fabian
python -m stellencrawler notify --dry-run  # Mail-Entwurf ohne Versand
python -m stellencrawler notify             # Mails versenden (SMTP in .env)
python -m stellencrawler crawl --notify     # Crawl + danach benachrichtigen
```

## Datenablage

| Pfad | Inhalt |
|------|--------|
| `data/jobs.db` | SQLite: `postings` (aktuell), `posting_history` (Versionen mit geänderten Feldern), `postings_fts` (Volltext) |
| `archive/pdf/` | Menschenlesbare PDFs der Ausschreibungen (`<interamt_id>.pdf`) |

## Versionierung & Pflege

Jede Änderung erhöht `VERSION` (SemVer), ergänzt `CHANGELOG.md`
(ausführlich, Keep a Changelog) und aktualisiert diese README –
Details in [`AGENTS.md`](AGENTS.md).

## Roadmap

- [x] SH-Landesstellensuche crawlen + archivieren (+ PDF)
- [x] Keyword-Filter pro Empfänger + E-Mail-Benachrichtigung (SMTP)
- [ ] Interamt-Crawler (Playwright, Apache Wicket)
- [ ] Zeitgesteuerter Lauf (Windows-Aufgabenplanung)
