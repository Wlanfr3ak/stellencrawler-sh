"""Tests fuer geo.py – PLZ-Extraktion, Distanz, Formatierung."""
import types

from stellencrawler import geo


class _FakeGeo:
    """Statische Koordinaten – kein Netzwerk/GeoNames nötig."""
    COORDS = {
        "24147": (54.32, 10.17),   # Kiel
        "20099": (53.55, 10.00),   # Hamburg
        "10117": (52.52, 13.39),   # Berlin
        "99999": (float("nan"), float("nan")),
    }

    def query_postal_code(self, plz):
        la, lo = self.COORDS.get(plz, (float("nan"), float("nan")))
        return types.SimpleNamespace(latitude=la, longitude=lo)


def _use_fake(monkeypatch):
    monkeypatch.setattr(geo, "_RES", _FakeGeo())


def test_plz_of_location():
    assert geo.plz_of("Harmsstraße, 24114 Kiel") == "24114"


def test_plz_of_fields_fallback():
    f = {"Arbeitsort": "Steinmetzstraße, 24534 Neumünster"}
    assert geo.plz_of(None, f) == "24534"


def test_plz_of_none():
    assert geo.plz_of(None, {}) is None
    assert geo.plz_of("Kiel") is None


def test_distance_km(monkeypatch):
    _use_fake(monkeypatch)
    d = geo.distance_km("24147", "20099")     # Kiel -> Hamburg
    assert d is not None and 75 < d < 105     # ~88 km
    assert geo.distance_km("24147", "10117") > 250
    assert geo.distance_km("24147", "24147") < 1
    assert geo.distance_km("24147", "99999") is None
    assert geo.distance_km(None, "24147") is None


def test_format_distance():
    assert geo.format_distance(None) is None
    assert geo.format_distance(3.2) == "ca. 3 km"
    assert geo.format_distance(48.7) == "ca. 50 km"   # >=15: auf 5 gerundet
