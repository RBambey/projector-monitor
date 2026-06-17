"""CSV data logger and alert file writer."""

from __future__ import annotations

import queue
import re
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from config import AppConfig, ProjectorConfig
    from poller import TempReading, TemperaturePoller

_CSV_HEADER = "timestamp,projector_label,projector_ip,sensor_index,temp_celsius,error\n"


class DataLogger:
    """Consumes TempReading events, writes to CSV, fires alerts on threshold breach."""

    def __init__(
        self,
        cfg: "AppConfig",
        poller: "TemperaturePoller",
        event_queue: queue.Queue,
    ) -> None:
        self._cfg = cfg
        self._poller = poller
        self._queue = event_queue
        self._log_file = None
        self._alert_dir: Optional[Path] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        # last alert time per projector IP (monotonic seconds)
        self._alert_cooldown: Dict[str, float] = {}
        self._alert_cooldown_secs = 300  # 5 minutes between alert dumps per projector

    def start(self) -> None:
        base = Path(__file__).parent / self._cfg.log_dir
        base.mkdir(parents=True, exist_ok=True)
        self._alert_dir = base / "alerts"
        self._alert_dir.mkdir(parents=True, exist_ok=True)

        log_path = base / "temps.csv"
        self._log_file = open(log_path, "a", newline="", buffering=1)
        if log_path.stat().st_size == 0:
            self._log_file.write(_CSV_HEADER)

        self._thread = threading.Thread(
            target=self._run, daemon=True, name="logger"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                reading: TempReading = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            self._write_csv(reading)
            self._check_alert(reading)

    def _write_csv(self, r: "TempReading") -> None:
        if self._log_file is None:
            return
        ts = r.timestamp.isoformat(timespec="seconds")
        temp = f"{r.temp_celsius:.1f}" if r.temp_celsius is not None else ""
        error = r.error or ""
        self._log_file.write(
            f"{ts},{r.projector_label},{r.projector_ip},"
            f"{r.sensor_index},{temp},{error}\n"
        )

    def _check_alert(self, r: "TempReading") -> None:
        if r.temp_celsius is None:
            return
        if r.temp_celsius <= self._cfg.temp_threshold:
            return
        now = time.monotonic()
        last = self._alert_cooldown.get(r.projector_ip, 0.0)
        if now - last < self._alert_cooldown_secs:
            return
        self._alert_cooldown[r.projector_ip] = now
        self._dump_alert(r)

    def _dump_alert(self, trigger: "TempReading") -> None:
        ts_str = trigger.timestamp.strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r"[^\w]", "_", trigger.projector_label)
        fname = self._alert_dir / f"alert_{ts_str}_{safe_label}.csv"

        all_buffers = self._poller.get_all_buffers()
        with open(fname, "w", newline="") as f:
            f.write(
                f"# ALERT: {trigger.projector_label} @ {trigger.projector_ip} "
                f"reached {trigger.temp_celsius:.1f}C "
                f"(threshold {self._cfg.temp_threshold:.1f}C)\n"
            )
            f.write(f"# Alert triggered: {trigger.timestamp.isoformat()}\n")
            f.write(_CSV_HEADER)
            for ip, readings in all_buffers.items():
                for r in readings:
                    ts = r.timestamp.isoformat(timespec="seconds")
                    temp = f"{r.temp_celsius:.1f}" if r.temp_celsius is not None else ""
                    error = r.error or ""
                    f.write(
                        f"{ts},{r.projector_label},{r.projector_ip},"
                        f"{r.sensor_index},{temp},{error}\n"
                    )
