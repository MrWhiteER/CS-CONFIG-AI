"""Visibility-gated adapter; the optional server module owns all operations."""

from __future__ import annotations

import copy
import time

try:
    from .. import serverlock
except ImportError:
    serverlock = None

_DEFAULT = object()


def display(status: dict) -> str:
    messages = []
    firewall = status.get("firewall") or {}
    if firewall.get("status") == "locked":
        messages.append(f"Locked to {firewall.get('city') or firewall.get('code') or 'region'}")
    if status.get("pending"):
        messages.append("Applies after you quit CS2")
    if status.get("needs_setup"):
        messages.append("Finish setup in the app to enable server region lock")
    if status.get("restart_needed"):
        messages.append("Restart CS2 to apply the region change")
    if status.get("error"):
        messages.append(str(status["error"]))
    if status.get("busy"):
        messages.append("Updating region lock…")
    return ". ".join(messages) or "No region lock"


class RegionLock:
    """No timers or threads. Call poll from the open panel, at most once/s."""

    def __init__(self, module=_DEFAULT, clock=time.monotonic):
        self.module = serverlock if module is _DEFAULT else module
        self.clock = clock
        self.visible = False
        self._next = 0.0
        self._status = {}
        self._regions = []

    def snapshot(self):
        if self.module is None:
            return {"available": False, "text": "Coming soon"}
        return copy.deepcopy({"available": True, "text": display(self._status),
                              "regions": self._regions, "status": self._status,
                              "poll": self.visible and bool(self._status.get("busy"))})

    def open(self):
        self.visible = True
        if self.module is not None:
            try:
                self._regions = self.module.list_regions()
                self._refresh()
            except Exception as exc:
                self._status = {"error": str(exc)}
        return self.snapshot()

    def close(self):
        self.visible = False

    def _refresh(self):
        self._next = self.clock() + 1
        try:
            self._status = self.module.lock_status()
        except Exception as exc:
            self._status = {"error": str(exc)}

    def poll(self):
        if (self.visible and self.module is not None and self._status.get("busy")
                and self.clock() >= self._next):
            self._refresh()
        return self.snapshot()

    def request(self, code=None):
        if not self.visible or self.module is None:
            raise ValueError("Open the panel to change the region lock")
        if self._status.get("busy"):
            raise ValueError("A region change is already in progress")
        if code is not None and code not in {r["code"] for r in self._regions}:
            raise ValueError("Choose a listed region")
        try:
            if code is None:
                self.module.request_unlock()
            else:
                self.module.request_lock(code)
            # Requests return immediately. Observe completion on a later poll.
            self._status = {**self._status, "busy": True, "error": ""}
            self._next = self.clock() + 1
        except Exception as exc:
            self._status = {"error": str(exc)}
        return self.snapshot()
