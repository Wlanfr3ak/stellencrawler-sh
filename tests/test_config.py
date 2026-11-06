"""Konfigurationsladen: Defaults, Overrides, Pfadaufloesung,
Versions-Warnung."""

import logging
from pathlib import Path

from stellencrawler import config


def test_defaults_without_config_file(tmp_path):
    cfg = config.load(tmp_path / "gibts-nicht.yaml")
    assert cfg["request_delay"] == 0.4
    assert cfg["queries"] == [""]
    assert cfg["recipients"] == []
    assert cfg["smtp"] == {}


def test_overrides_and_path_resolution(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text(
        "request_delay: 1.5\n"
        "database: x/j.db\n"
        "recipients:\n  - email: a@b.de\n    keywords: [Informatik]\n",
        encoding="utf-8")
    cfg = config.load(f)
    assert cfg["request_delay"] == 1.5
    assert cfg["database"] == config.ROOT / "x" / "j.db"
    assert cfg["recipients"][0]["keywords"] == ["Informatik"]


def test_absolute_paths_untouched(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text(f"database: {tmp_path.as_posix()}/abs.db\n", encoding="utf-8")
    cfg = config.load(f)
    assert cfg["database"] == Path(str(tmp_path / "abs.db"))


def test_version_mismatch_warns(tmp_path, caplog):
    f = tmp_path / "c.yaml"
    f.write_text('version: "0.0.1"\n', encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        config.load(f)
    assert "version" in caplog.text.lower()


def test_user_agent_version_placeholder(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text('user_agent: "bot/{version} (kontakt: a@b.de)"\n',
                 encoding="utf-8")
    cfg = config.load(f)
    expected = (config.ROOT / "VERSION").read_text().strip()
    assert cfg["user_agent"] == f"bot/{expected} (kontakt: a@b.de)"


def test_version_match_no_warning(tmp_path, caplog):
    f = tmp_path / "c.yaml"
    expected = (config.ROOT / "VERSION").read_text().strip()
    f.write_text(f'version: "{expected}"\n', encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        config.load(f)
    assert not caplog.records
