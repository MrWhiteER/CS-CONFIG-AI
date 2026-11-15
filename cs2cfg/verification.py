"""Read-back of Apply's recorded expectations. Never repairs or elevates.

Only ``save`` writes, and only to the app's own receipt during Apply. Checking
an existing receipt performs reads exclusively, including when access fails.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import cfglang, scaling, steam


def save(path: Path, receipt: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(receipt), encoding="utf-8")
    temporary.replace(path)


def load(path: Path):
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict) or not isinstance(receipt.get("checks"), list):
            return None
        if "applied_at" not in receipt or any(not isinstance(x, dict) or
                "kind" not in x or "label" not in x for x in receipt["checks"]):
            return None
        return receipt
    except (OSError, ValueError):
        return None


def check(receipt: dict | None) -> dict:
    if not receipt:
        return {"ok": True, "items": [], "total": 0, "verified": 0}
    items = []
    for spec in receipt["checks"]:
        item = {"label": spec["label"], "status": "not_checked",
                "detail": spec.get("detail", ""), "counted": spec.get("counted", True)}
        try:
            kind = spec["kind"]
            if kind == "unavailable":
                pass
            elif spec.get("failed"):
                item.update(status="failed", detail=spec["failed"])
            else:
                if kind == "video":
                    user = steam.SteamUser("0", Path(spec["user"]))
                    # Force an actual read even when Steam's reader accepts a
                    # missing file as an empty config. PermissionError remains
                    # distinct from a readable value which changed.
                    user.video_cfg.read_text(encoding="utf-8")
                    actual = steam.read_video_cfg(user).get(spec["key"])
                    matches = actual == spec["expected"]
                elif kind == "launch":
                    user = steam.SteamUser("0", Path(spec["user"]))
                    user.localconfig.read_text(encoding="utf-8")
                    matches = steam.read_launch_options(user) == spec["expected"]
                elif kind == "text":
                    matches = Path(spec["path"]).read_text(encoding="utf-8") == spec["expected"]
                elif kind == "exec":
                    doc = cfglang.parse(Path(spec["path"]).read_text(encoding="utf-8"))
                    matches = any(c.lname == "exec" and c.arg(0) and
                                  c.arg(0).text.replace("\\", "/").lower() == spec["expected"].lower()
                                  for line in doc.lines for c in line.commands)
                elif kind == "scaling":
                    report = scaling.read()
                    if not report.available or not report.screens:
                        raise PermissionError(report.reason or "Display settings unavailable")
                    screen = next((s for s in report.screens
                                   if s.display_id == spec.get("display_id")), None)
                    if screen is None and spec.get("display_id") is None:
                        screen = report.primary
                    if screen is None:
                        raise PermissionError("Applied display unavailable")
                    matches = (screen.scaling == spec["expected"] if "expected" in spec
                               else screen.fills)
                else:
                    raise ValueError("Unknown check")
                item.update(status="verified" if matches else "changed",
                            detail="Matches the applied value" if matches else
                            "Changed or missing since Apply. Review and apply again.")
        except PermissionError:
            item.update(status="not_checked", detail="Not checked: access unavailable. No extra rights requested.")
        except FileNotFoundError:
            item.update(status="changed", detail="File is missing since Apply.")
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            item.update(status="not_checked", detail=f"Not checked: {exc}")
        items.append(item)
    counted = [x for x in items if x["counted"]]
    return {"ok": True, "items": items, "total": len(counted),
            "verified": sum(x["status"] == "verified" for x in counted),
            "applied_at": receipt["applied_at"], "checked_at": time.time(),
            "selection": receipt.get("selection"),
            "storage_warning": receipt.get("storage_warning"),
            "account": receipt.get("account"), "intent": receipt.get("intent")}
