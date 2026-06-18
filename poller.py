"""Background polling threads — one per projector, rolling 1-hour buffer each."""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from config import AppConfig, ProjectorConfig
from http_client import ProjectorWebClient, WebClientError
from protocol import PJLinkError, ProjectorClient


@dataclass
class TempReading:
    timestamp: datetime
    projector_label: str
    projector_ip: str
    sensor_index: int
    temp_celsius: float | None
    error: str | None       # e.g. "TIMEOUT", "AUTH_FAILED", "CONN_REFUSED"
    sensor_name: str = ""   # e.g. "light1", "exhaust", or "s0" for PJLink sensor 0


class TemperaturePoller:
    """One daemon thread per projector; all readings go to a shared queue."""

    def __init__(self, cfg: AppConfig, event_queue: queue.Queue) -> None:
        self._cfg = cfg
        self._queue = event_queue
        self._buffers: Dict[str, deque] = {}
        self._threads: List[threading.Thread] = []
        self._stop = threading.Event()

    def start(self) -> None:
        for proj in self._cfg.projectors:
            if not proj.enabled:
                continue
            self._start_one(proj)

    def stop(self) -> None:
        self._stop.set()

    def get_buffer(self, ip: str) -> List[TempReading]:
        return list(self._buffers.get(ip, deque()))

    def get_all_buffers(self) -> Dict[str, List[TempReading]]:
        return {ip: list(buf) for ip, buf in self._buffers.items()}

    def latest(self, ip: str) -> Optional[TempReading]:
        buf = self._buffers.get(ip)
        return buf[-1] if buf else None

    def add_projector(self, proj: ProjectorConfig) -> None:
        if proj.ip in self._buffers:
            return
        self._start_one(proj)

    # ------------------------------------------------------------------

    def _start_one(self, proj: ProjectorConfig) -> None:
        # Multiply by 8: each poll appends one entry per sensor (up to ~8).
        # Without this a 4-sensor projector fills the buffer 4× too fast.
        capacity = int(self._cfg.rolling_buffer_minutes * 60 / self._cfg.poll_interval) * 8
        self._buffers[proj.ip] = deque(maxlen=capacity)
        t = threading.Thread(
            target=self._poll_loop, args=(proj,),
            daemon=True, name=f"poller-{proj.ip}",
        )
        self._threads.append(t)
        t.start()

    def _poll_loop(self, proj: ProjectorConfig) -> None:
        # Prefer HTTP web client; fall back to PJLink if no web credentials
        if proj.web_username or proj.web_password:
            client = ProjectorWebClient(proj)
            use_http = True
        else:
            client = ProjectorClient(proj)
            use_http = False

        while not self._stop.is_set():
            start = time.monotonic()
            readings = self._do_poll_http(client, proj) if use_http \
                       else self._do_poll_pjlink(client, proj)
            for r in readings:
                self._buffers[proj.ip].append(r)
                try:
                    self._queue.put_nowait(r)
                except queue.Full:
                    pass
            elapsed = time.monotonic() - start
            self._stop.wait(timeout=max(0.0, self._cfg.poll_interval - elapsed))

    def _do_poll_http(self, client: ProjectorWebClient, proj: ProjectorConfig) -> List[TempReading]:
        ts = datetime.now()
        try:
            temps = client.query_temperatures()  # {sensor_name: float}
            return [
                TempReading(ts, proj.label, proj.ip, i, temp, None, name)
                for i, (name, temp) in enumerate(temps.items())
            ]
        except TimeoutError:
            return [TempReading(ts, proj.label, proj.ip, 0, None, "TIMEOUT")]
        except ConnectionError as e:
            return [TempReading(ts, proj.label, proj.ip, 0, None, f"CONN_ERR")]
        except WebClientError as e:
            return [TempReading(ts, proj.label, proj.ip, 0, None, str(e))]
        except Exception as e:
            return [TempReading(ts, proj.label, proj.ip, 0, None, f"ERR:{e}")]

    def _do_poll_pjlink(self, client: ProjectorClient, proj: ProjectorConfig) -> List[TempReading]:
        ts = datetime.now()
        try:
            temps = client.query_temperature()
            return [
                TempReading(ts, proj.label, proj.ip, i, t, None, f"s{i}")
                for i, t in enumerate(temps)
            ]
        except TimeoutError:
            return [TempReading(ts, proj.label, proj.ip, 0, None, "TIMEOUT")]
        except ConnectionRefusedError:
            return [TempReading(ts, proj.label, proj.ip, 0, None, "CONN_REFUSED")]
        except PJLinkError as e:
            return [TempReading(ts, proj.label, proj.ip, 0, None, str(e))]
        except OSError as e:
            return [TempReading(ts, proj.label, proj.ip, 0, None, f"OSERR:{e}")]
