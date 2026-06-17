from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

_DEFAULT_IP = "192.168.48.110"
_CONFIG_PATH = Path(__file__).parent / "config.json"


@dataclass
class ProjectorConfig:
    label: str
    ip: str
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
            ProjectorConfig(label="Projector 1", ip=_DEFAULT_IP)
        ]
    )


def load_config(path: str | Path = _CONFIG_PATH) -> AppConfig:
    p = Path(path)
    if not p.exists():
        cfg = _default_config()
        save_config(cfg, p)
        return cfg
    data = json.loads(p.read_text())
    projectors = [ProjectorConfig(**d) for d in data.get("projectors", [])]
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
