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
from protocol import PJLinkError, ProjectorClient


@dataclass
class TempReading:
    timestamp: datetime
    projector_label: str
    projector_ip: str
    sensor_index: int
    temp_celsius: float | None
    error: str | None  # "TIMEOUT", "ERR3", "CONN_REFUSED", etc.


class TemperaturePoller:
    """One daemon thread per projector; all readings go to a shared queue."""

    def __init__(self, cfg: AppConfig, event_queue: queue.Queue) -> None:
        self._cfg = cfg
        self._queue = event_queue
        # keyed by IP; each deque holds at most (buffer_minutes * 60 / poll_interval) entries
        self._buffers: Dict[str, deque] = {}
        self._threads: List[threading.Thread] = []
        self._stop = threading.Event()

    def start(self) -> None:
        for proj in self._cfg.projectors:
            if not proj.enabled:
                continue
            capacity = int(
                self._cfg.rolling_buffer_minutes * 60 / self._cfg.poll_interval
            )
            self._buffers[proj.ip] = deque(maxlen=capacity)
            t = threading.Thread(
                target=self._poll_loop,
                args=(proj,),
                daemon=True,
                name=f"poller-{proj.ip}",
            )
            self._threads.append(t)
            t.start()

    def stop(self) -> None:
        self._stop.set()

    def get_buffer(self, ip: str) -> List[TempReading]:
        return list(self._buffers.get(ip, deque()))

    def get_all_buffers(self) -> Dict[str, List[TempReading]]:
        return {ip: list(buf) for ip, buf in self._buffers.items()}

    def latest(self, ip: str) -> Optional[TempReading]:
        buf = self._buffers.get(ip)
        if buf:
            return buf[-1]
        return None

    def add_projector(self, proj: ProjectorConfig) -> None:
        """Add and start polling a new projector at runtime."""
        if proj.ip in self._buffers:
            return
        capacity = int(
            self._cfg.rolling_buffer_minutes * 60 / self._cfg.poll_interval
        )
        self._buffers[proj.ip] = deque(maxlen=capacity)
        t = threading.Thread(
            target=self._poll_loop,
            args=(proj,),
            daemon=True,
            name=f"poller-{proj.ip}",
        )
        self._threads.append(t)
        t.start()

    # ------------------------------------------------------------------

    def _poll_loop(self, proj: ProjectorConfig) -> None:
        client = ProjectorClient(proj)
        while not self._stop.is_set():
            start = time.monotonic()
            for reading in self._do_poll(client, proj):
                self._buffers[proj.ip].append(reading)
                try:
                    self._queue.put_nowait(reading)
                except queue.Full:
                    pass  # logger is behind; drop rather than block the poll thread
            elapsed = time.monotonic() - start
            self._stop.wait(timeout=max(0.0, self._cfg.poll_interval - elapsed))

    def _do_poll(self, client: ProjectorClient, proj: ProjectorConfig) -> List[TempReading]:
        ts = datetime.now()
        try:
            temps = client.query_temperature()
            return [
                TempReading(ts, proj.label, proj.ip, i, t, None)
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
