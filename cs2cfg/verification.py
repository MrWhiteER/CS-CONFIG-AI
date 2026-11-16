"""Read-back of Apply's values and recommended system settings. Never elevates.

Only ``save`` writes, and only to the app's own receipt during Apply. Checking
an existing receipt performs reads exclusively, including when access fails.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from . import cfglang, nvidia, quickfix, scaling, steam, wingraphics


def system_checks(install: Path | None, data_dir: Path | None = None) -> list:
    return [
        {"label": "NVIDIA profile", "kind": "nvidia"},
        {"label": "Windows power", "kind": "power",
         "record": str(data_dir / quickfix.POWER_RECORD) if data_dir else None},
        {"label": "Windows graphics", "kind": "wingraphics",
         "install": str(install) if install else None},
    ]


def with_system_checks(receipt: dict | None, install: Path | None, data_dir: Path | None = None):
    """Upgrade old receipts in memory, including their three excluded placeholders."""
    if not receipt:
        return None
    additions = system_checks(install, data_dir)
    labels = {s["label"] for s in additions}
    return {**receipt, "checks": [s for s in receipt["checks"] if s["label"] not in labels] + additions}


def _power_matches(record_path: str | None = None) -> bool:
    if sys.platform != "win32":
        raise RuntimeError("Windows power settings unavailable")
    report = quickfix._powercfg(["/getactivescheme"], timeout=5)
    found = quickfix._GUID_RE.search(report["out"])
    if not report["ok"] or not found:
        raise RuntimeError(report.get("error") or "Active power scheme could not be read")
    active = found.group(1).lower()
    # SCHEME_MIN is the fix's documented fallback; Ultimate may have a new GUID.
    if active in {"8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", quickfix.ULTIMATE_TEMPLATE_GUID}:
        return True
    try:
        # Use the directory resolved at app startup. Calling user_data_dir here
        # could perform its write probe; even that is forbidden during a check.
        record = json.loads(Path(record_path).read_text(encoding="utf-8")) if record_path else {}
        if record.get("active") and active == str(record.get("changed_to", "")).lower():
            return True
    except (OSError, ValueError, AttributeError):
        pass
    # Same discovery rule as the existing fix, without its create/setactive path.
    listed = quickfix._powercfg(["/list"], timeout=5)
    if not listed["ok"]:
        raise RuntimeError(listed.get("error") or "Power schemes could not be read")
    return any(guid.lower() == active and name.strip().lower() == "ultimate performance"
               for guid, name in quickfix._SCHEME_LINE_RE.findall(listed["out"]))


def _system_check(spec: dict, item: dict) -> None:
    kind = spec["kind"]
    item["action"] = kind
    if kind == "nvidia":
        report = nvidia.read_recommended()
        if report.get("not_applicable"):
            item.update(status="not_applicable", counted=False,
                        detail="No NVIDIA GPU/driver. Excluded from the count.")
            item.pop("action")
            return
        if not report["available"]:
            raise RuntimeError(report.get("reason") or "NVIDIA profile unavailable")
        matches = report["matches"]
        detail = ("In NVIDIA Control Panel > Manage 3D settings > Program Settings > cs2.exe: " +
                  report["detail"] + ".")
    elif kind == "power":
        matches = _power_matches(spec.get("record"))
        detail = "Choose Ultimate Performance in Fix It (High performance is also accepted)."
    else:
        if sys.platform != "win32":
            raise RuntimeError("Windows graphics settings unavailable")
        exe = wingraphics.exe_path(Path(spec["install"]) if spec.get("install") else None)
        if exe is None:
            raise RuntimeError("CS2's executable was not found")
        actual = wingraphics.read(exe, strict=True)
        matches = actual == wingraphics.wanted(actual)
        detail = "Use Set for performance in Settings > Apply > Machine."
    item.update(status="verified" if matches else "not_set",
                detail="Matches the recommended settings" if matches else detail)
    if matches:
        item.pop("action")


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
            if kind in {"nvidia", "power", "wingraphics"}:
                _system_check(spec, item)
            elif kind == "unavailable":
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
