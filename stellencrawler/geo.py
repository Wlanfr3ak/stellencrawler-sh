"""Grobe Luftlinien-Entfernung zwischen deutschen PLZs.

Nutzt pgeocode (GeoNames-Daten, werden beim ersten Aufruf einmalig
heruntergeladen und gecacht). Liefert bewusst nur grobe Werte –
genug fuer "ist das in Pendelreichweite".
"""

import json
import math
import re

_PLZ_RE = re.compile(r"\b(\d{5})\b")

_RES = None  # pgeocode.Nominatim-Instanz (lazy; in Tests ersetzbar)


def _geo():
    global _RES
    if _RES is None:
        import pgeocode
        _RES = pgeocode.Nominatim("de")
    return _RES


def plz_of(location: str | None, fields: dict | None = None) -> str | None:
    """Erste 5-stellige PLZ aus location bzw. Feldwerten extrahieren.
    Feldnamen mit 'arbeitsort'/'einsatzort' werden bevorzugt."""
    m = _PLZ_RE.search(location or "")
    if m:
        return m.group(1)
    f = fields or {}
    for k in ("arbeitsort", "einsatzort"):
        for kk, v in f.items():
            if k in kk.lower():
                m = _PLZ_RE.search(str(v))
                if m:
                    return m.group(1)
    for v in f.values():
        m = _PLZ_RE.search(str(v))
        if m:
            return m.group(1)
    return None


def distance_km(plz_a: str | None, plz_b: str | None) -> float | None:
    """Luftlinien-Entfernung in km (Haversine) oder None."""
    if not plz_a or not plz_b:
        return None
    try:
        g = _geo()
        a, b = g.query_postal_code(str(plz_a)), g.query_postal_code(str(plz_b))
        if any(math.isnan(float(x)) for x in
               (a.latitude, a.longitude, b.latitude, b.longitude)):
            return None
        p1, p2 = math.radians(a.latitude), math.radians(b.latitude)
        dp, dl = p2 - p1, math.radians(b.longitude - a.longitude)
        h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 6371.0 * 2 * math.asin(math.sqrt(h))
    except Exception:
        return None


def distance_of(row, home_plz: str | None) -> float | None:
    """Entfernung home_plz -> Arbeitsort der Stelle (postings-Row)."""
    if not home_plz:
        return None
    try:
        fields = json.loads(row["fields_json"] or "{}")
    except Exception:
        fields = {}
    return distance_km(home_plz, plz_of(row["location"], fields))


def format_distance(km: float | None) -> str | None:
    """Grobe Angabe: <15 km auf 1 km, sonst auf 5 km gerundet."""
    if km is None:
        return None
    km = round(km) if km < 15 else int(5 * round(km / 5))
    return f"ca. {km} km"
