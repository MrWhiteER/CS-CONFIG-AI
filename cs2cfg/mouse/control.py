"""The app's mouse setting: what the player chose, and putting it on the mouse.

``mouse_dpi`` / ``mouse_poll`` are 0 until the player picks something, which
means "leave the mouse as it is". They travel with cloud sync, so a new PC
sets a new (or the same) mouse the same way as soon as the app starts there.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Mapping, Optional

from .base import Brand, Reading

DEFAULTS: Dict[str, int] = {"mouse_dpi": 0, "mouse_poll": 0}
POLL_CHOICES = (125, 250, 500, 1000, 2000, 4000, 8000)


def read_settings(ui: Optional[Mapping[str, Any]] = None, *, strict: bool = False) -> dict:
    ui = ui or {}
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        if key not in ui:
            continue
        value = ui[key]
        ok = isinstance(value, int) and not isinstance(value, bool)
        if ok and key == "mouse_dpi":
            ok = value == 0 or 100 <= value <= 50000
        if ok and key == "mouse_poll":
            ok = value == 0 or value in POLL_CHOICES
        if ok:
            out[key] = value
        elif strict:
            raise ValueError("That mouse speed or polling rate isn't one the app can use.")
    return out


def default_brands() -> List[Brand]:
    from .razer import Razer

    # SteelSeries and HyperX go here as they are added, each talking to its
    # own mice directly.
    return [Razer()]


def _took(mouse: Reading, settings: Mapping[str, Any]) -> bool:
    dpi, poll = settings.get("mouse_dpi"), settings.get("mouse_poll")
    if dpi and mouse.dpi != min(dpi, mouse.max_dpi):
        return False
    if poll and poll in mouse.rates and mouse.poll != poll:
        return False
    return True


class MouseControl:
    """Reads and sets every mouse the brands find. One job at a time."""

    def __init__(self, brands: Optional[Callable[[], List[Brand]]] = None) -> None:
        self._brands = brands or default_brands
        self._lock = threading.Lock()
        self.last: List[Reading] = []
        self.problem = ""
        self.retries, self.retry_every = 10, 30.0
        self._wake = threading.Event()   # set only by tests, to skip waiting

    def _each(self):
        for brand in self._brands():
            yield brand

    def find(self) -> List[Reading]:
        with self._lock:
            found: List[Reading] = []
            self.problem = ""
            for brand in self._each():
                try:
                    found.extend(brand.find())
                except OSError as exc:
                    self.problem = f"Mice could not be listed: {exc}"
            self.last = found
            return found

    def apply(self, settings: Mapping[str, Any]) -> List[Reading]:
        """Put the chosen speed and rate on every mouse found. 0 = leave it."""
        dpi = settings.get("mouse_dpi") or None
        poll = settings.get("mouse_poll") or None
        with self._lock:
            out: List[Reading] = []
            self.problem = ""
            for brand in self._each():
                try:
                    mice = brand.find()
                except OSError as exc:
                    self.problem = f"Mice could not be listed: {exc}"
                    continue
                for mouse in mice:
                    if dpi is None and poll is None:
                        out.append(mouse)
                        continue
                    wanted_poll = poll if poll in mouse.rates else None
                    try:
                        out.append(brand.set(mouse.id, dpi, wanted_poll))
                    except (OSError, LookupError) as exc:
                        mouse.problem = str(exc)
                        out.append(mouse)
            self.last = out
            return out

    def apply_later(self, settings: Mapping[str, Any]) -> None:
        """Apply in the background (app start, after a cloud pull)."""
        if not (settings.get("mouse_dpi") or settings.get("mouse_poll")):
            return

        def run():
            # A wireless mouse that is asleep, or a receiver Windows is still
            # setting up, doesn't answer at first: try again for a few minutes.
            for attempt in range(self.retries):
                try:
                    mice = self.apply(settings)
                except Exception:
                    mice = []   # a mouse is never worth crashing over
                if mice and all(_took(m, settings) for m in mice):
                    return
                if attempt + 1 < self.retries:
                    self._wake.wait(self.retry_every)
        threading.Thread(target=run, name="mouse-apply", daemon=True).start()

    def status(self, settings: Mapping[str, Any]) -> Dict[str, Any]:
        return {"settings": dict(settings),
                "mice": [m.as_dict() for m in self.last],
                "problem": self.problem}
