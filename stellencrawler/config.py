import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "database": "data/jobs.db",
    "pdf_dir": "archive/pdf",
    "request_delay": 0.4,
    "user_agent": "stellencrawler/0.x (privates Stellenarchiv; "
                  "Kontakt bitte in config.yaml hinterlegen)",
    "queries": [""],
    "recipients": [],
    "smtp": {},
}


def load(path: Path | None = None) -> dict:
    cfg = dict(DEFAULTS)
    cfg_path = path or ROOT / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            cfg.update(yaml.safe_load(f) or {})
    for key in ("database", "pdf_dir"):
        p = Path(cfg[key])
        if not p.is_absolute():
            p = ROOT / p
        cfg[key] = p
    cfg["root"] = ROOT
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if "{version}" in str(cfg.get("user_agent", "")):
        cfg["user_agent"] = cfg["user_agent"].replace("{version}", expected)
    if str(cfg.get("version", "")) != expected:
        log.warning("config.yaml: version=%s, Programmversion=%s – "
                    "bitte config.yaml.version mitpflegen",
                    cfg.get("version"), expected)
    return cfg
