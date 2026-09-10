"""Knowledge base: hardware tier data and the CS2 settings matrix.

The bundled JSON under ``knowledge/`` is the source of truth. Anything the
user updates or calibrates lands in ``%APPDATA%/cs2-autoconfig/knowledge``
and is merged on top, so a local correction survives reinstalling the tool.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import app_dir, bundle_root, is_frozen, storage_kind  # noqa: F401

BUNDLED = bundle_root() / "knowledge"
FILES = ("gpus.json", "cpus.json", "video_settings.json", "launch_options.json")


def user_data_dir() -> Path:
    """Re-exported so callers do not all need to know about paths.py."""
    from .paths import user_data_dir as _resolve

    return _resolve()


def user_knowledge_dir() -> Path:
    return user_data_dir() / "knowledge"


class KnowledgeError(RuntimeError):
    """A knowledge file is missing or malformed."""


@dataclass
class Match:
    """Result of looking a part up in the tier tables."""

    index: float
    matched: Optional[str]
    exact: bool
    note: str = ""
    entry: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.entry is None:
            self.entry = {}


def normalise(name: str) -> str:
    """Flatten a marketing name into something matchable.

    ``12th Gen Intel(R) Core(TM) i9-12900K`` becomes
    ``12th gen intel core i9-12900k``.
    """
    text = name.lower()
    text = re.sub(r"\((?:r|tm|c)\)", " ", text)
    text = text.replace("™", " ").replace("®", " ")
    text = re.sub(r"\b(nvidia|amd|intel|geforce|radeon|graphics card|laptop gpu)\b", r" \1 ", text)
    text = re.sub(r"[^a-z0-9+\-. ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens_match(haystack: str, tokens: List[str]) -> bool:
    """Every token must appear as a whole word."""
    for token in tokens:
        if not re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", haystack):
            return False
    return True


def _best_entry(haystack: str, entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pick the entry matching the most tokens, so 3090 Ti beats 3090."""
    best: Optional[Dict[str, Any]] = None
    best_len = -1
    for entry in entries:
        tokens = entry.get("tokens") or []
        if tokens and _tokens_match(haystack, tokens) and len(tokens) > best_len:
            best, best_len = entry, len(tokens)
    return best


class KnowledgeBase:
    """Loads, merges and queries the knowledge files."""

    def __init__(self, extra_dir: Optional[Path] = None) -> None:
        self.extra_dir = extra_dir or user_knowledge_dir()
        self.gpus = self._load("gpus.json")
        self.cpus = self._load("cpus.json")
        self.video = self._load("video_settings.json")
        self.launch = self._load("launch_options.json")
        self._apply_overrides()

    # -- loading ----------------------------------------------------------
    def _load(self, filename: str) -> Dict[str, Any]:
        path = BUNDLED / filename
        if not path.exists():
            raise KnowledgeError(f"bundled knowledge file missing: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise KnowledgeError(f"{filename} is not valid JSON: {exc}") from exc

        override = self.extra_dir / filename
        if override.exists():
            try:
                patch = json.loads(override.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return data  # a corrupt override must never break a run
            data = _deep_merge(data, patch)
        return data

    def _apply_overrides(self) -> None:
        """Fold calibrated key ranges into the video settings tables."""
        calib = self.extra_dir / "calibration.json"
        if not calib.exists():
            return
        try:
            observed = json.loads(calib.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        for key, seen_max in (observed.get("observed_max") or {}).items():
            spec = self.video.get("keys", {}).get(key)
            if spec and isinstance(seen_max, int) and seen_max > spec.get("max", 0):
                spec["max"] = seen_max
                spec["confidence"] = "calibrated"

    # -- lookups ----------------------------------------------------------
    def match_gpu(self, name: str) -> Match:
        hay = normalise(name)
        entry = _best_entry(hay, self.gpus.get("gpus", []))
        if entry:
            return Match(
                index=float(entry["index"]),
                matched=" ".join(entry["tokens"]).upper(),
                exact=True,
                entry=entry,
            )

        for fallback in self.gpus.get("series_fallback", []):
            pattern = fallback.get("pattern")
            hit = re.search(pattern, hay) if pattern else _tokens_match(hay, fallback.get("tokens", []))
            if hit:
                return Match(
                    index=float(fallback["index"]),
                    matched=None,
                    exact=False,
                    note=fallback.get("note", "estimated from series"),
                    entry=fallback,
                )

        return Match(index=15.0, matched=None, exact=False, note="unrecognised GPU; assumed entry level")

    def match_cpu(self, name: str, max_clock_mhz: int = 0) -> Match:
        hay = normalise(name)
        entry = _best_entry(hay, self.cpus.get("cpus", []))
        if entry:
            return Match(
                index=float(entry["st"]),
                matched=" ".join(entry["tokens"]).upper(),
                exact=True,
                entry=entry,
            )

        fb = self.cpus.get("clock_fallback", {})
        if max_clock_mhz:
            est = max_clock_mhz * float(fb.get("mhz_to_index", 0.019))
            est = max(float(fb.get("floor", 30)), min(float(fb.get("ceiling", 85)), est))
            return Match(
                index=est,
                matched=None,
                exact=False,
                note=f"unrecognised CPU; estimated from {max_clock_mhz} MHz peak clock",
            )
        return Match(index=float(fb.get("floor", 30)), matched=None, exact=False, note="unrecognised CPU")

    # -- updating ---------------------------------------------------------
    def update(self, url: str, timeout: int = 20) -> Tuple[List[str], str]:
        """Fetch a knowledge bundle and install it as a local override.

        The bundle is a single JSON object keyed by filename. Nothing is
        written until every member has parsed and passed a schema check, so a
        truncated download cannot leave a half-updated knowledge base behind.
        """
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise KnowledgeError(f"could not reach {url}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise KnowledgeError(f"update at {url} was not valid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise KnowledgeError("update bundle must be a JSON object keyed by filename")

        staged: Dict[str, str] = {}
        for filename, content in payload.items():
            if filename not in FILES:
                continue
            if not isinstance(content, dict) or "schema" not in content:
                raise KnowledgeError(f"{filename} in the bundle has no schema field")
            staged[filename] = json.dumps(content, indent=2)

        if not staged:
            raise KnowledgeError("update bundle contained none of the expected files")

        self.extra_dir.mkdir(parents=True, exist_ok=True)
        for filename, text in staged.items():
            (self.extra_dir / filename).write_text(text, encoding="utf-8")

        return sorted(staged), str(self.extra_dir)

    def reset_overrides(self) -> bool:
        """Delete local overrides and go back to the bundled tables."""
        if self.extra_dir.exists():
            shutil.rmtree(self.extra_dir)
            return True
        return False

    def clamp(self, key: str, value: int) -> int:
        """Hold a value inside the range the knowledge base declares for it."""
        spec = self.video.get("keys", {}).get(key)
        if not spec:
            return value
        allowed = spec.get("allowed")
        if allowed:
            return min(allowed, key=lambda a: (abs(a - value), a > value))
        return max(int(spec.get("min", 0)), min(int(spec.get("max", value)), value))

    def label(self, key: str, value: int) -> str:
        """Human-readable name for a setting value, e.g. 4 -> '4x MSAA'."""
        spec = self.video.get("keys", {}).get(key, {})
        labels = spec.get("labels") or {}
        return labels.get(str(value), str(value))

    def ui_name(self, key: str) -> str:
        spec = self.video.get("keys", {}).get(key, {})
        return spec.get("ui") or key.replace("setting.videocfg_", "").replace("setting.", "").replace("_", " ").title()


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
