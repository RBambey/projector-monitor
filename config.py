from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

_DEFAULT_IP = "192.168.48.110"


def _app_data_dir() -> Path:
    """Return the writable data directory for config and logs.

    Inside a PyInstaller .app bundle sys.frozen is True and __file__ resolves
    into the read-only bundle, so we redirect to Application Support instead.
    """
    if getattr(sys, 'frozen', False):
        d = Path.home() / "Library" / "Application Support" / "Projector Monitor"
    else:
        d = Path(__file__).parent
    d.mkdir(parents=True, exist_ok=True)
    return d


_CONFIG_PATH = _app_data_dir() / "config.json"


@dataclass
class ProjectorConfig:
    label: str
    ip: str
    # Web interface credentials (Digest auth) — used for HTTP temperature polling
    web_username: str = ""
    web_password: str = ""
    # PJLink fallback (port 4352) — only used if web credentials are absent
    port: int = 4352
    auth_password: str = ""
    enabled: bool = True


@dataclass
class AppConfig:
    projectors: List[ProjectorConfig]
    temp_threshold: float = 70.0
    poll_interval: int = 10
    log_dir: str = "logs"
    rolling_buffer_minutes: int = 60


def _default_config() -> AppConfig:
    return AppConfig(
        projectors=[
            ProjectorConfig(
                label="Projector 1",
                ip=_DEFAULT_IP,
                web_username="sfjazz",
                web_password="sfjazz12345",
            )
        ]
    )


def load_config(path: str | Path = _CONFIG_PATH) -> AppConfig:
    p = Path(path)
    if not p.exists():
        cfg = _default_config()
        save_config(cfg, p)
        return cfg
    data = json.loads(p.read_text())
    projectors = [
        ProjectorConfig(
            label=d.get("label", d.get("ip", "?")),
            ip=d.get("ip", ""),
            web_username=d.get("web_username", ""),
            web_password=d.get("web_password", ""),
            port=d.get("port", 4352),
            auth_password=d.get("auth_password", ""),
            enabled=d.get("enabled", True),
        )
        for d in data.get("projectors", [])
    ]
    if not projectors:
        projectors = _default_config().projectors
    return AppConfig(
        projectors=projectors,
        temp_threshold=float(data.get("temp_threshold", 70.0)),
        poll_interval=int(data.get("poll_interval", 10)),
        log_dir=data.get("log_dir", "logs"),
        rolling_buffer_minutes=int(data.get("rolling_buffer_minutes", 60)),
    )


def save_config(cfg: AppConfig, path: str | Path = _CONFIG_PATH) -> None:
    data = {
        "projectors": [asdict(p) for p in cfg.projectors],
        "temp_threshold": cfg.temp_threshold,
        "poll_interval": cfg.poll_interval,
        "log_dir": cfg.log_dir,
        "rolling_buffer_minutes": cfg.rolling_buffer_minutes,
    }
    Path(path).write_text(json.dumps(data, indent=2))
