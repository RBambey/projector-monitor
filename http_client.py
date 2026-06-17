"""HTTP temperature client for Panasonic PT-series projectors.

Scrapes the web status page (/cgi-bin/projector_status.cgi) using Digest auth.
Returns named temperature readings for all sensors reported by the projector.
Falls back to PJLink if web credentials are not configured.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Dict

import requests
from requests.auth import HTTPDigestAuth

if TYPE_CHECKING:
    from config import ProjectorConfig

# Pattern: "LIGHT1 TEMPERATURE 65" or "INTAKE AIR TEMPERATURE 21"
_TEMP_RE = re.compile(
    r'(LIGHT\d+|INTAKE AIR|EXHAUST AIR)\s+TEMPERATURE\s+(\d+)\s*(?:&deg;|°)',
    re.IGNORECASE,
)

_SENSOR_NAMES = {
    "INTAKE AIR":  "intake",
    "EXHAUST AIR": "exhaust",
    "LIGHT1":      "light1",
    "LIGHT2":      "light2",
    "LIGHT3":      "light3",
    "LIGHT4":      "light4",
}


class WebClientError(Exception):
    pass


class ProjectorWebClient:
    TIMEOUT = 6.0
    STATUS_PATH = "/cgi-bin/projector_status.cgi?lang=e"

    def __init__(self, cfg: "ProjectorConfig") -> None:
        self.cfg = cfg
        self._url = f"http://{cfg.ip}{self.STATUS_PATH}"
        self._auth = HTTPDigestAuth(cfg.web_username, cfg.web_password)

    def query_temperatures(self) -> Dict[str, float]:
        """Return {sensor_name: temp_celsius} for all sensors on the status page.

        Raises:
            WebClientError: auth failed, page unreachable, or no temps found
            TimeoutError: request timed out
            ConnectionError: host unreachable
        """
        try:
            resp = requests.get(self._url, auth=self._auth,
                                timeout=self.TIMEOUT)
        except requests.exceptions.Timeout:
            raise TimeoutError(f"HTTP timeout to {self.cfg.ip}")
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"HTTP connect failed: {e}")

        if resp.status_code == 401:
            raise WebClientError("AUTH_FAILED — check web username/password in setup")
        if not resp.ok:
            raise WebClientError(f"HTTP {resp.status_code}")

        return self._parse_temps(resp.text)

    @staticmethod
    def _parse_temps(body: str) -> Dict[str, float]:
        text = re.sub(r'<[^>]+>', ' ', body)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'\s+', ' ', text)

        results: Dict[str, float] = {}
        for m in _TEMP_RE.finditer(text):
            raw_name = m.group(1).upper().strip()
            temp = float(m.group(2))
            name = _SENSOR_NAMES.get(raw_name, raw_name.lower().replace(" ", "_"))
            results[name] = temp

        if not results:
            raise WebClientError("no temperature data found on status page")

        return results
