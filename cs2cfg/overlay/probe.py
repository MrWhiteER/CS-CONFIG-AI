"""CLI-only one-second JSONL measurement runner."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from .presentmon import Aggregator, PresentMon, STATUS_TEXT


def run(seconds: int | None = None, no_hud: bool = False,
        exclude_from_capture: bool = False) -> int:
    from .metrics import Metrics

    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    output = root / "cs2cfg" / "overlay-probe" / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Overlay probe output: {output}", flush=True)
    aggregator = Aggregator()
    presentmon = PresentMon(aggregator)
    metrics = hud = None
    interrupted = False
    try:
        with output.open("x", encoding="utf-8") as stream:
            metrics = Metrics()
            presentmon.start()
            if not no_hud:
                from .hud import Hud

                hud = Hud(exclude_from_capture)
                hud.update({"status": "PresentMon: waiting for frame data"})
                hud.start()
                if hud.warning:
                    print(f"HUD: {hud.warning}", flush=True)
            started = time.monotonic()
            tick = started + 1
            end = started + seconds if seconds is not None else float("inf")
            wait = threading.Event()
            previous_status = None
            while tick <= end:
                wait.wait(max(0.0, tick - time.monotonic()))
                sample = aggregator.snapshot()
                position = metrics.game.find()
                running = position is not None
                state = presentmon.status(running, bool(sample["frame_count"]))
                status = STATUS_TEXT[state]
                if not running and state != "not_found":
                    status += "; cs2.exe not found"
                sample.update(metrics.sample())
                sample.update({
                    "at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                    "elapsed_seconds": time.monotonic() - started,
                    "status": status,
                    "game_status": "running" if running else "not_found",
                    "presentmon_status": state,
                    "presentmon_exit_code": presentmon.process.poll() if presentmon.process else None,
                    "presentmon_stderr": presentmon.stderr,
                    "presentmon_session": presentmon.session,
                    "hud_visible": hud.visible if hud else False,
                    "hud_status": (hud.error or hud.warning or "ok") if hud else "disabled",
                })
                if hud:
                    hud.update(sample, position or (20, 20))
                stream.write(json.dumps(sample, allow_nan=False) + "\n")
                stream.flush()
                if status != previous_status:
                    print(status, flush=True)
                    previous_status = status
                # Preserve one-second boundaries; skip missed ticks if sampling
                # was delayed, rather than emitting a burst of empty intervals.
                tick += 1
                now = time.monotonic()
                if tick < now:
                    tick += int(now - tick) + 1
    except KeyboardInterrupt:
        interrupted = True
    finally:
        # Independent cleanup so an unexpected HUD failure cannot strand ETW.
        try:
            if hud:
                hud.stop()
        finally:
            try:
                presentmon.stop()
            finally:
                if metrics:
                    metrics.close()
    print("Overlay probe stopped.", flush=True)
    return 130 if interrupted else 0
