"""PJLink Class 2 TCP client for querying projector temperature."""

from __future__ import annotations

import hashlib
import socket
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from config import ProjectorConfig


class PJLinkError(Exception):
    """Raised when the projector returns a PJLink error code."""


class ProjectorClient:
    TIMEOUT = 3.0

    def __init__(self, cfg: "ProjectorConfig") -> None:
        self.cfg = cfg

    def query_temperature(self) -> List[float]:
        """Return a list of temperatures (°C), one per internal sensor.

        Opens a fresh TCP connection each call — more resilient than persistent
        connections across the projector's sleep/wake cycle.

        Raises:
            TimeoutError: socket connect or read timed out
            ConnectionRefusedError: nothing listening on the port
            PJLinkError: projector returned an error code (e.g. ERR3 = unsupported)
        """
        sock = self._connect_and_auth()
        try:
            sock.sendall(self._cmd(b"%2TMPR ?"))
            response = self._readline(sock)
        finally:
            sock.close()

        return self._parse_tmpr(response)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect_and_auth(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.TIMEOUT)
        try:
            sock.connect((self.cfg.ip, self.cfg.port))
        except socket.timeout as e:
            sock.close()
            raise TimeoutError(f"connect timeout to {self.cfg.ip}:{self.cfg.port}") from e

        greeting = self._readline(sock)
        self._token = self._parse_greeting(greeting)
        return sock

    def _parse_greeting(self, line: bytes) -> bytes:
        """Return the auth token prefix (empty bytes if no auth required)."""
        text = line.decode("ascii", errors="replace").strip()
        parts = text.split()
        # "PJLINK 0"         → no auth
        # "PJLINK 1 <seed>"  → auth required
        if len(parts) >= 2 and parts[1] == "1":
            if len(parts) < 3:
                raise PJLinkError("PJLINK auth required but no seed provided")
            seed = parts[2]
            digest = hashlib.md5(
                (seed + self.cfg.auth_password).encode("ascii")
            ).hexdigest()
            return digest.encode("ascii")
        return b""

    def _cmd(self, command: bytes) -> bytes:
        return self._token + command + b"\r"

    @staticmethod
    def _readline(sock: socket.socket, maxbytes: int = 256) -> bytes:
        buf = b""
        while len(buf) < maxbytes:
            try:
                ch = sock.recv(1)
            except socket.timeout as e:
                raise TimeoutError("read timeout") from e
            if not ch:
                break
            buf += ch
            if ch == b"\r":
                break
        return buf

    @staticmethod
    def _parse_tmpr(response: bytes) -> List[float]:
        """Parse "%2TMPR=45+47\r" → [45.0, 47.0]."""
        text = response.decode("ascii", errors="replace").strip()
        # Strip any leading auth token (32 hex chars before the %)
        if "%" in text:
            text = text[text.index("%"):]

        if not text.startswith("%2TMPR="):
            raise PJLinkError(f"unexpected response: {text!r}")

        value = text[len("%2TMPR="):]

        if value.startswith("ERR"):
            raise PJLinkError(value)

        temps = []
        for part in value.split("+"):
            part = part.strip()
            if part:
                try:
                    temps.append(float(part))
                except ValueError:
                    raise PJLinkError(f"non-numeric temperature value: {part!r}")

        if not temps:
            raise PJLinkError("empty temperature response")

        return temps
