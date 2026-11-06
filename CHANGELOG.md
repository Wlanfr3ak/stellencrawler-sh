# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [0.10.2] – 2026-11-06

### Fixed

- **PDF-Export: Server-Fehlerseiten werden nicht mehr archiviert.**
  Fuer 5 Stellen lagen PDFs vor, die nur eine Varnish-Fehlerseite
  enthielten ("Error 503 Backend fetch failed" – der Server hatte
  beim Massenexport gedrosselt). `pdf.py` prueft jetzt nach dem Laden
  Titel+Body auf typische Fehlermarker ("fetch failed", "Error 5xx",
  "not found" u. a.); eine Fehlerseite wird uebersprungen statt ins
  Archiv geschrieben – die fehlende Datei wird beim naechsten Lauf
  automatisch erneut versucht. Die 5 defekten Dateien wurden entfernt
  (`python -m stellencrawler pdf` holt sie nach).
- Tests: `_page_failed`-Erkennung (Fake-Page) – insgesamt 49 Tests.
- `PyMuPDF` als Dev-Abhaengigkeit (manuelle QA der PDF-Textebene).

## [0.10.1] – 2026-11-06

### Fixed

- `config.example.yaml`: `home_plz` enthielt die echte private PLZ
  des Empfaengers – auf 24105 (Schleswig-Holsteinischer Landtag, Kiel)
  als neutrales Beispiel geaendert.

## [0.10.0] – 2026-11-06

### Added

- **`title_keywords` pro Empfaenger**: dritte Keyword-Ebene neben
  `keywords` (Volltext) und `exclude_title` (Negativ-Titel). Begriffe
  darin matchen **nur im Titel** – gedacht fuer Suchwoerter, die im
  Fliesstext rauschen ('EDV-Kenntnisse', 'Netzwerk aufbauen' =
  Kooperation, 'IT-Sicherheitsgesetz'). Trefferlogik:
  `(keywords ODER title_keywords) UND NICHT exclude_title`.
- **Entfernungsangabe je Stelle** (`stellencrawler/geo.py`): pro
  Empfaenger konfigurierbare `home_plz`; PLZ des Arbeitsorts wird aus
  `location`/`Arbeitsort`/`Einsatzort`-Feld extrahiert und die grobe
  Luftlinien-Entfernung (Haversine ueber GeoNames-PLZ-Zentroide via
  `pgeocode`, Daten werden einmalig gecacht) berechnet. Gerundet auf
  1 km (<15) bzw. 5 km. Anzeige als eigene Zeile in `matches`-
  Trefferliste und in der Mail (HTML: '📍 ca. N km Luftlinie' in der
  Stelle-Zelle; Plaintext: eigene Zeile je Stelle). Keine PLZ/
  kein Geocoding -> Zeile faellt weg.
- Fabian (`config.yaml`): Keywords aufgeteilt (starke -> `keywords`,
  rauschende -> `title_keywords`), `exclude_title` um studentisch/
  Referendar/Praktikum erweitert, `home_plz: "24147"` gesetzt.
  Ergebnis 49 -> **19 Treffer** (plus 3 zuvor uebersehene, z. B.
  'IT-Fachpruefer Datenzugriff').
- Abhaengigkeit `pgeocode>=0.4,<1` (GeoNames-PLZ-Daten).
- Tests: `test_geo.py` (PLZ-Extraktion, Haversine mit Fake-Resolver,
  Formatierung) + `title_keywords`- und `home_plz`-Matching-Tests in
  `test_notify.py` – insgesamt 47 Tests.

### Changed

- `matches`-Ausgabe zeigt `title_keywords` als `[Titel]`-Zeilen und
  die Entfernung als eigene Zeile je Stelle an.

## [0.9.0] – 2026-11-06

### Changed

- **`job_types` umbenannt zu `exclude_title` und Semantik umgekehrt**:
  die zweite Keyword-Gruppe ist jetzt ein **Negativ-Filter** – Stellen,
  deren Titel einen der Begriffe enthaelt, werden NICHT gemeldet
  (z. B. Ausbildung/Auszubildende/Duales Studium/Werkstudent
  ausschliessen). Zuvor war sie ein Einschluss-Filter (AND-Bedingung).
  Weiterhin nur-Titel-Match, da die Begriffe im Volltext fast ueberall
  als Anforderung stehen und dann fast alles aussortieren wuerden.
- `matches`-Kommando zeigt Ausschluss-Treffer jetzt als
  `[ausschl.] <kw> -> N ausgeschlossen`.
- Fabian: gleiche Begriffliste, neue Wirkung – Treffermenge von 56
  auf 49 (die 7 Ausbildungs-/Duales-Studium-Stellen fliegen raus).
- `config.yaml`-Migration manuell: `job_types:` unter `recipients` in
  `exclude_title:` umbenennen (Vorlage in `config.example.yaml`).
- Test umgebaut: `test_recipient_matches_exclude_title` – deckt jetzt
  auch ab, dass 'Ausbildung' im Fließtext NICHT ausschliesst
  (nur Titel). Weiterhin 40 Tests.

## [0.8.0] – 2026-11-06

### Added

- **Stellenart-Filter pro Empfaenger** (`job_types:` unter `recipients`):
  optionale zweite Keyword-Gruppe. Eine Stelle gilt dann nur als Treffer,
  wenn mind. 1 `keyword` (Volltext) **UND** mind. 1 `job_type` matcht.
  `job_types` werden **nur gegen den Titel** geprueft – Begriffe wie
  "Ausbildung" stehen im Volltext als Anforderung in fast jeder Anzeige
  und wuerden sonst nicht filtern. Ohne `job_types` bleibt das bisherige
  Verhalten (nur Keywords) erhalten.
- `store.match_keyword(conn, kw, column='title')`: FTS5-Spaltenfilter,
  mit dem Suchen auf eine einzelne Indexspalte einschraenkbar sind.
- `matches`-Kommando zeigt `job_types`-Treffer separat mit `[Titel]`-
  Prefix an, damit der Filter beim Tunen sichtbar ist.
- Fabian in `config.yaml` eingegrenzt: `job_types` = Ausbildung,
  Auszubildende, Duales Studium, Werkstudent -> Treffermenge von 56
  auf 7 Stellen (alles Ausbildungs-/Duales-Studium-Anzeigen mit IT-
  Bezug). Achtung: `ausbildung*` matcht `auszubildende*` **nicht**
  (verschiedene Wortstaemme) – beide Begriffe sind noetig.
- Tests: `test_match_keyword_column_title` (Store),
  `test_recipient_matches_job_types` (Notify) – insgesamt 40 Tests.

## [0.7.1] – 2026-11-06

### Added

- **`{version}`-Platzhalter im `user_agent`**: wird beim Laden der
  Config automatisch durch die aktuelle VERSION-Nummer ersetzt – der
  User-Agent zeigt damit immer die Programmversion, ohne Pflege.
  Test in `test_config.py` ergaenzt (insgesamt 38 Tests).

### Fixed

- `config.yaml`: beim Umschreiben der Datei war die hinterlegte
  Kontakt-E-Mail im `user_agent` auf den Platzhalter zurueckgefallen –
  wiederhergestellt.

## [0.7.0] – 2026-11-06

### Added

- **Test-Suite** (`tests/`, 37 Tests): Quertests ueber alle Ebenen –
  - `test_parsing.py`: Formular-Hidden-Felder, Teaser-Extraktion,
    Paginierung, Detailseite (echte Fixture-HTMLs in `tests/fixtures/`),
    Toleranz bei kaputtem HTML.
  - `test_store.py`: Upsert new/unchanged/updated, Historie inkl.
    Snapshot, FTS-Reindex, Removed-/Reaktivierungs-Logik,
    Keyword-Matching (Praefix + AND), Notifications-Dedupe,
    Schema-Migration.
  - `test_config.py`: Defaults, Overrides, Pfadaufloesung,
    Versions-Warnung.
  - `test_notify.py`: Empfaenger-Matching, `_job_cells`
    (Stunden/Entgelt/Ort/Mobil-Erkennung), HTML-Tabellen-Mail mit
    Escaping, Dry-Run, Versand-Dedupe, SMTP STARTTLS/SSL (gemockt).
  - `test_e2e.py`: kompletter Zyklus (Crawl -> Archiv -> Matching ->
    Mail -> Removed-Markierung) gegen lokalen HTTP-Fixture-Server –
    kein Live-Traffic, zweiter Lauf ohne Duplikate.
- `requirements-dev.txt` (pytest), Ausfuehrung: `python -m pytest tests/`.
- AGENTS.md: Testpflicht als 4. verbindliche Regel verankert.
- `posting_history.snapshot_json`: vollstaendiger Snapshot des alten
  Stands bei jeder Aenderung (bisher nur fields+Text – Titel-/Kontakt-
  Aenderungen gingen verloren). Schema-Migration `user_version` 3.

### Fixed

- PDF-Export: `wait_until="load"` statt `"networkidle"` – die Seite
  haelt teils Verbindungen offen, wodurch `goto` in Timeouts lief.

## [0.6.0] – 2026-11-06

### Added

- **HTML-Tabelle in der Benachrichtigungs-Mail**: eine Zeile pro Stelle
  mit den Spalten Stelle (Titel + Behoerde + getroffene Keywords),
  Std./Woche, Entgelt, Arbeitsort, Mobil? (erkennt "mobiles Arbeiten",
  "Homeoffice", "Telearbeit", "hybrid", "remote" u. a. im Anzeigentext)
  und Link. Plain-Text-Fallback bleibt fuer Mailclients ohne HTML.
- **Versionsnummer auch in `config.yaml`** (`version:`-Schluessel);
  Regel in AGENTS.md verankert: VERSION-Datei + config.yaml +
  config.example.yaml werden gemeinsam hochgezaehlt.
- `config.load()` warnt, falls `config.yaml.version` von der
  VERSION-Datei abweicht.

## [0.5.0] – 2026-11-06

### Changed

- **SMTP-Zugangsdaten liegen jetzt in `config.yaml`** (`smtp:`-Block:
  host, port, user, password, from) statt in einer separaten `.env` –
  komplette Konfiguration an einem Ort. Da `config.yaml` gitignoriert
  ist, bleiben die Credentials geschuetzt. `notify` bricht mit
  Fehlermeldung ab, falls `smtp.host` fehlt (Dry-Run geht weiterhin
  ohne Zugang).

### Removed

- `.env` / `.env.example` und Abhaengigkeit `python-dotenv`
  (keine zweite Config-Quelle mehr).

## [0.4.0] – 2026-11-06

### Added

- **Benachrichtigungs-Modul** (`stellencrawler/notify.py`): pro
  Empfaenger eigene Keyword-Liste (`recipients` in `config.yaml`).
  Matching laeuft lokal ueber den FTS5-Index – mit Praefix-Suche
  (`informatik*` trifft auch "Informatiker") und AND-Verknuepfung
  mehrteiliger Begriffe ("IT-Forensik" -> `it* AND forensik*`).
  Dadurch unabhaengig von den Suchformularen und wechselnden
  Begrifflichkeiten der Portale.
- **Notifications-Tabelle** (`notifications`): merkt pro Empfaenger,
  welche Stellen bereits gemeldet wurden – keine Doppel-Mails.
  Dry-Run schreibt nichts.
- **CLI**: `notify [--dry-run]` (Mails versenden bzw. nur anzeigen),
  `matches [--recipient X] [--top N]` (Preview: Treffer je Keyword +
  Stellenliste zum Tunen der Suchbegriffe), `crawl --notify`.
- SMTP-Versand via `smtplib` (STARTTLS :587 / SSL :465), Zugangsdaten
  aus `.env` (`SMTP_HOST/PORT/USER/PASSWORD/FROM`).
- FTS-Index um **Feldwerte** erweitert (Entgelt, Aufgabenbereiche,
  Beschaeftigungsverhaeltnis u. a. enthalten relevante Begriffe);
  automatische Migration beim ersten Connect (PRAGMA `user_version`).

### Changed

- `config.yaml`: `keywords` ersetzt durch `recipients`-Liste
  (name, email, keywords) – mehrere Personen mit eigenen Suchprofilen.
- `.env.example`: `MAIL_FROM/MAIL_TO` -> `SMTP_FROM` (Empfaenger stehen
  jetzt in `config.yaml`).

## [0.3.0] – 2026-11-06

### Added

- **Konfigurierbarer User-Agent** (`user_agent` in `config.yaml`):
  identifiziert den Crawler gegenueber den Portal-Betreibern mit Zweck
  und Kontakt-E-Mail, damit Admins bei Problemen Kontakt aufnehmen
  koennen. Wird bei allen HTTP-Requests des Crawlers und im
  Playwright-Browser des PDF-Exports gesendet (zuvor fest codierter
  String bzw. Chromium-Default `HeadlessChrome`).
- `config.yaml` als lokale, gitignorierte Konfigurationsdatei mit
  `config.example.yaml` als Vorlage.

### Changed

- `sh_land.new_session(user_agent)` und `pdf.export_pdfs(user_agent)`
  nehmen den UA jetzt als Parameter entgegen; `crawl`/`pdf`-Kommandos
  reichen den Config-Wert durch.
- `.gitignore` um `config.yaml` ergaenzt.

## [0.2.1] – 2026-11-06

### Fixed

- **PDF-Export**: exportierte PDFs wirkten ausgebleicht/gedimmt, weil das
  Cookie-Consent-Modal (`#cookiebanner`, Body-Klasse `banner-visible`)
  als Abdunklung ueber der Seite lag und mitgedruckt wurde. Der Export
  klickt nun vor dem Druck auf "Alle auswaehlen"; falls der Button nicht
  auffindbar ist, werden Banner-Element und CSS-Klasse per JS entfernt.
  Alle zuvor erzeugten PDFs wurden mit dem Fix neu exportiert.

## [0.2.0] – 2026-11-06

### Added

- **SH-Crawler** (`stellencrawler/sources/sh_land.py`): durchsucht die
  Stellensuche des Landesportals komplett (leere Suchanfrage = alle
  Stellen, 100 Treffer/Seite, Sortierung nach Veröffentlichungsdatum).
  Berücksichtigt die signierten Hidden-Felder (`callerId.HASH`,
  `__time_token`) und die doppelt URL-enkodierte `gtp`-Paginierung.
  Detailseiten werden ueber `data-testid`-Marker und eingebettetes
  JSON-LD (`JobPosting`) geparst: Titel, Behoerde, alle Metafelder,
  Anzeigentext (HTML + Text), Kontakt inkl. E-Mail, `datePosted` und
  "Letzte Aktualisierung".
- **SQLite-Archiv** (`stellencrawler/store.py`, `data/jobs.db`):
  Tabelle `postings` (aktueller Stand, Schluessel `interamt_<id>`),
  `posting_history` (Versionierung: bei Inhaltsaenderung Snapshot mit
  Liste geaenderter Felder), `postings_fts` (FTS5-Volltextindex ueber
  Titel/Behoerde/Ort/Beschreibung). Nicht mehr gelistete Stellen werden
  als `removed` markiert und bleiben im Archiv.
- **PDF-Export** (`stellencrawler/pdf.py`): speichert Detailseiten als
  menschenlesbares PDF via Playwright/Chromium `page.pdf()` (nutzt das
  Print-CSS der Seite, entspricht "Seite drucken") nach `archive/pdf/<id>.pdf`.
- **CLI** (`python -m stellencrawler`): `crawl [--pdf] [--limit N]`,
  `pdf`, `list`, `search <query>`, `show <id> [--full]`.
- `config.example.yaml`, `.env.example`, `.gitignore`, `requirements.txt`.

### Changed

- `AGENTS.md`: Datenquellen-Befunde praezisiert (SH-Portal spiegelt
  Interamt-Inserate; Hidden-Felder-Pflicht; JSON-LD), Modulstruktur auf
  Ist-Stand gebracht, PDF-Archivierung ergaenzt.
- Parser-Bibliothek: `lxml` entfernt (kein Wheel fuer Python 3.15),
  Parsing laeuft ueber `html.parser` (stdlib).

## [0.1.0] – 2026-11-06

### Added

- Projektinitialisierung: `AGENTS.md` mit verbindlichen Projektregeln
  (Versionierung, Changelog-Pflicht, README-Pflicht), technischem Kontext
  zu den Datenquellen (schleswig-holstein.de Stellensuche, interamt.de)
  und dokumentierter Recherche zu existierenden Referenzprojekten.
- `VERSION` als alleinige Quelle der Versionsnummer, `README.md` und
  dieses Changelog angelegt.
