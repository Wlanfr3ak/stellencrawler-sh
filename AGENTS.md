# AGENTS.md – Stellencrawler Schleswig-Holstein

Dieses Dokument enthält die verbindlichen Projektregeln und den technischen
Kontext für alle (menschlichen und agentischen) Beitragenden.

## 1. Projektziel

Ein Python-Tool, das **regelmäßig die Stellenangebote des Landes
Schleswig-Holstein crawlt** und bei **neuen Stellen** bzw. Treffern auf
konfigurierbare **Suchwörter eine Benachrichtigungs-E-Mail** versendet.

### Datenquellen

| Quelle | URL | Bemerkung |
|--------|-----|-----------|
| Landesportal SH – Stellensuche | https://www.schleswig-holstein.de/SiteGlobals/Forms/Stellensuche/Stellensuche_Formular.html | GET-Formular, serverseitig gerendert. Implementiert in `sources/sh_land.py`. Wichtig: Hidden-Felder (`callerId` + signierter `callerId.HASH`, `__time_token`) müssen aus frisch geladenem Formular mitgeschickt werden. Leerer `templateQueryString` = alle Stellen; `resultsPerPage=100`; Paginierung über **doppelt URL-enkodierten** `gtp`-Parameter (`_list%253D<N>`). Detailseiten unter `/SiteGlobals/Functions/Interamt/Stellenausschreibung?id=interamt_<id>` – **die Landesstellen sind gespiegelte Interamt-Inserate** (gleicher ID-Raum!). Parsebar via `data-testid`-Marker + `JobPosting`-JSON-LD (enthält Volltext und `datePosted`). |
| Interamt.de | https://www.interamt.de/ | Größte Jobbörse des öffentlichen Dienstes (Bund/Länder/Kommunen). Läuft auf **Apache Wicket** (stateful, Session-basiert); reines HTTP-Scraping scheitert häufig an Redirect-Loops → voraussichtlich **Playwright** (Headless Browser) erforderlich. Für Behörden existiert eine offizielle Connector-API (XML/Webservice, benötigt Behörden-ID). |

### Funktionale Anforderungen

- Regelmäßiger Lauf (z. B. täglich) via Windows-Aufgabenplanung / cron.
- Persistenter Speicher bereits gesehener Stellen (Dedupe) in SQLite
  (`data/jobs.db`): `postings` (aktuell), `posting_history`
  (Versionen mit geänderten Feldern), `postings_fts` (FTS5-Volltext).
  Nicht mehr gelistete Stellen → `status='removed'`, bleiben archiviert.
- **PDF-Archiv:** pro Stelle zusätzlich ein menschenlesbares PDF der
  Detailseite (`archive/pdf/<id>.pdf`, Playwright `page.pdf()`,
  entspricht der "Seite drucken"-Funktion des Portals).
- **Keyword-Filter pro Empfänger** (`recipients` in `config.yaml`:
  name, email, keywords, optional `title_keywords`, `exclude_title`,
  `home_plz`). Matching lokal via FTS5: Präfix-Suche, mehrteilige
  Begriffe = AND. Logik: `(keywords ODER title_keywords) UND NICHT
  exclude_title`. `keywords` matchen im Volltext; `title_keywords` nur
  im Titel (Begriffe, die im Fließtext rauschen: „EDV-Kenntnisse",
  „Netzwerk aufbauen"); `exclude_title` ist Negativ-Filter nur auf den
  Titel (Ausbildung & Co. stehen im Volltext fast überall als
  Anforderung). `home_plz` erzeugt eine grobe Luftlinien-Entfernung je
  Stelle (`geo.py`, pgeocode/GeoNames-Zentroide). Tabelle
  `notifications` verhindert Doppel-Mails. `matches` = Tuning-Preview.
- E-Mail-Versand via SMTP (Zugangsdaten in `config.yaml` `smtp:`,
  niemals committen).

## 2. Verbindliche Regeln für jede Änderung

Diese Regeln gelten **bei jeder einzelnen Änderung** am Projekt – ohne
Ausnahme:

1. **Versionsnummer hochzählen**
   - Versionsschema: [Semantic Versioning](https://semver.org/lang/de/)
     (`MAJOR.MINOR.PATCH`).
   - Die aktuelle Version steht in der Datei `VERSION` (einzelne Zeile,
     z. B. `0.2.0`). Sie ist die einzige Quelle der Wahrheit.
   - **Zusätzlich** ist `version:` in `config.yaml` (und in
     `config.example.yaml`) auf denselben Stand zu bringen. Der Code
     warnt beim Laden, falls beide auseinanderlaufen.
   - Im `user_agent` (config.yaml) steht der Platzhalter `{version}`,
     der beim Laden automatisch ersetzt wird – dort ist also **nichts**
     manuell zu pflegen.
   - Richtwerte: Bugfix → PATCH, neues Feature (rückwärtskompatibel) →
     MINOR, Breaking Change → MAJOR.

2. **Changelog pflegen**
   - `CHANGELOG.md` im Format [Keep a Changelog](https://keepachangelog.com/de/1.1.0/)
     führen: neuer Abschnitt `## [x.y.z] – YYYY-MM-DD` mit den Kategorien
     `Added`, `Changed`, `Fixed`, `Removed`, `Deprecated`, `Security`.
   - **Ausführlich** schreiben: Was wurde geändert, warum, und welche
     Auswirkungen hat es (Konfiguration, Datenformat, Verhalten).

3. **README.md nachpflegen**
   - `README.md` muss nach jeder Änderung den tatsächlichen Stand
     widerspiegeln (Setup, Nutzung, Konfiguration, Features).
   - Veraltete Angaben in der README gelten als Fehler und sind sofort
     zu korrigieren.

4. **Ausführliche Quertests pflegen und erweitern**
   - Bei jeder Änderung sind die Tests in `tests/` anzupassen **und**
     um sinnvolle neue Fälle zu erweitern – quer über alle Ebenen:
     Parsing (echte Fixture-HTMLs), Store (Upsert/Historie/FTS/
     Removed/Notifications), Config, Mail-Aufbau/Versand und der
     End-to-End-Lauf gegen den lokalen Fixture-Server.
   - `python -m pytest tests/` muss **grün** sein, bevor eine Änderung
     als fertig gilt. Testabhängigkeiten stehen in
     `requirements-dev.txt`.

Eine Änderung gilt erst als abgeschlossen, wenn alle vier Punkte erfüllt
sind.

## 3. Technischer Stack & Konventionen

- **Sprache:** Python 3 (möglichst ≥ 3.11).
- **Abhängigkeiten liegen im Projektordner:**
  - Virtuelle Umgebung als `.venv/` im Projektverzeichnis
    (`python -m venv .venv`).
  - `requirements.txt` ist stets aktuell zu halten
    (`pip freeze > requirements.txt` nach jeder Installation).
  - `.venv/`, `data/`, `.env` und `__pycache__/` gehören in `.gitignore`.
- **Konfiguration:** komplett in `config.yaml` (gitignoriert!):
  `user_agent`, `request_delay`, `queries`, `recipients` (Empfänger
  mit eigenen Keywords), `smtp` (Zugangsdaten). `config.example.yaml`
  im Repo als Vorlage ohne echte Daten. **Keine** `.env` mehr.
- **Logging:** `logging`-Modul, Logdatei unter `logs/`.
- **Code-Stil:** kompakt, idiomatisch, Typannotationen wo sinnvoll;
  keine übermäßige Fehlerbehandlung, aber robuste Grenzen gegenüber
  Netzwerk/Parsing-Fehlern (ein kaputtes Angebot darf den Lauf nicht
  abbrechen).

### Modulstruktur

```
stellencrawler/
  __init__.py          # __version__ aus VERSION-Datei
  __main__.py          # CLI: crawl [--pdf] [--limit], pdf, list, search, show
  config.py            # config.yaml + Defaults
  sources/
    sh_land.py         # Crawler schleswig-holstein.de (requests + BS4)
    interamt.py        # Crawler interamt.de (Playwright) – geplant
  store.py             # SQLite-Archiv: postings + posting_history + FTS5
                       #   + notifications (bereits benachrichtigt)
  pdf.py               # PDF-Export via Playwright/Chromium
  geo.py               # PLZ->Koordinaten (pgeocode/GeoNames) + Haversine
  notify.py            # Keyword-Matching + SMTP-Versand pro Empfaenger
```

## 4. Recherche-Stand: existierende Projekte

Vor der Eigenentwicklung wurde recherchiert (Stand: 2026-11-06). Es gibt
**kein fertiges Projekt**, das genau diesen Zweck erfüllt (SH-Stellensuche
+ Interamt + Keyword-Mail). Relevante Referenzen:

- [giessmann1/interamtdb](https://github.com/giessmann1/interamtdb) –
  Python-Scraper für interamt.de in eine MongoDB (Forschungsdatenbank).
  Wertvoll als Referenz für Interamt-Parsing/Aufbau.
- [WSBusch/interamt_connect](https://github.com/WSBusch/interamt_connect) –
  TYPO3-Extension, die die **offizielle Interamt-API** (Connector-
  Webservice, Behörden-ID nötig) nutzt. Belegt: Es gibt eine API, aber
  primär für teilnehmende Behörden.
- [RRZE-Webteam/rrze-jobs](https://github.com/RRZE-Webteam/rrze-jobs) –
  WordPress-Plugin, bindet u. a. Interamt über API ein.
- career-ops Issue
  ([santifer/career-ops#698](https://github.com/santifer/career-ops/issues/698)) –
  dokumentiert, warum interamt.de ohne Browser-Session kaum scrapebar
  ist (Wicket), und schlägt Playwright vor. Bestätigt unsere
  Technikwahl.
- [rizzn/JOBSTER](https://github.com/rizzn/JOBSTER) – Multi-Portal-
  Job-Crawler (Python), deckt aber weder Interamt noch die SH-
  Landesseite ab.
- Hinweis: Beide Portale bieten native E-Mail-Abos (interamt „Jobabo").
  Der eigene Crawler ist trotzdem sinnvoll, um **beide Quellen
  einheitlich** zu deduplizieren und beliebige Keyword-Logik
  abzubilden.
