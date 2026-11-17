"""What every lighting backend offers the sync loop."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from .palette import Frame

# Local APIs only. A system proxy must never see (or break) a call to
# localhost, so requests here never go through one.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_json(method: str, url: str, body: Any = None, timeout: float = 2.0) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with _OPENER.open(req, timeout=timeout) as resp:
        raw = resp.read()
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        return None


class Provider:
    """One lighting API.

    ``probe`` is cheap and safe: it only asks whether the API is there, and
    changes no light. ``start`` takes control, ``apply`` paints a frame,
    ``keepalive`` is called every few seconds while running, and ``stop``
    hands the lights back to the vendor's own software.
    """

    id = ""
    name = ""
    # Vendors whose devices this provider drives itself, so a catch-all
    # provider can leave them alone instead of fighting over them.
    vendors: tuple = ()

    def __init__(self) -> None:
        self.active = False
        self.devices: list = []
        self.why = ""

    def probe(self) -> bool:
        raise NotImplementedError

    def start(self) -> None:
        raise NotImplementedError

    def apply(self, frame: Frame) -> None:
        raise NotImplementedError

    def keepalive(self) -> None:
        pass

    def stop(self) -> None:
        raise NotImplementedError

    def status(self) -> dict:
        return {"id": self.id, "name": self.name, "active": self.active,
                "devices": list(self.devices), "why": self.why}


def owner_vendors(providers) -> set:
    out: set = set()
    for p in providers:
        if p.active:
            out.update(v.lower() for v in p.vendors)
    return out


