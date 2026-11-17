"""Small Valve GSI receiver and the single owned game configuration file."""

from __future__ import annotations

import hmac
import json
import secrets
import time
from pathlib import Path

MAX_BODY = 64 * 1024
CFG_NAME = "gamestate_integration_cs2cfg.cfg"
COMPONENTS = ("provider", "map", "round", "player_id", "player_state")


def install_token(directory: Path) -> str:
    """Persist an independent secret; never expose it in snapshots or UI prefs."""
    path = directory / "overlay-gsi-token"
    try:
        token = path.read_text(encoding="ascii").strip()
        if len(token) == 64 and all(c in "0123456789abcdef" for c in token):
            return token
    except (FileNotFoundError, UnicodeError):
        pass
    directory.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    path.write_text(token, encoding="ascii")
    return token


def write_cfg(install: Path, port: int, token: str) -> Path:
    if not 1 <= port <= 65535 or len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise ValueError("Invalid GSI configuration")
    path = Path(install) / "game" / "csgo" / "cfg" / CFG_NAME
    # Do not create game directories or follow a file redirected elsewhere.
    if path.is_symlink() or not path.parent.is_dir():
        raise OSError("CS2 cfg directory unavailable")
    data = '\n'.join(f'        "{key}" "1"' for key in COMPONENTS)
    path.write_text(
        '"CS2 Auto Config"\n{\n'
        f'    "uri" "http://127.0.0.1:{port}/api/overlay/gsi"\n'
        '    "timeout" "2.0"\n    "buffer" "0.1"\n    "throttle" "0.5"\n'
        '    "heartbeat" "5.0"\n'
        f'    "auth" {{ "token" "{token}" }}\n    "data"\n    {{\n{data}\n    }}\n}}\n',
        encoding="utf-8")
    return path


def remove_cfg(install: Path) -> None:
    (Path(install) / "game" / "csgo" / "cfg" / CFG_NAME).unlink(missing_ok=True)


def parse_payload(raw: bytes, token: str) -> dict:
    if len(raw) > MAX_BODY:
        raise ValueError("GSI body too large")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Invalid GSI JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("Expected GSI object")
    auth = body.get("auth")
    supplied = auth.get("token") if isinstance(auth, dict) else None
    if not (token and isinstance(supplied, str) and supplied.isascii()
            and hmac.compare_digest(supplied, token)):
        raise PermissionError("Invalid GSI token")

    def pick(value, keys):
        if not isinstance(value, dict):
            return {}
        return {k: v for k, v in value.items() if k in keys
                and isinstance(v, (str, int, float)) and not isinstance(v, bool)}

    player = body.get("player")
    player = player if isinstance(player, dict) else {}
    return {"provider": pick(body.get("provider"), ("appid", "steamid")),
            "map": pick(body.get("map"), ("name", "phase")),
            "round": pick(body.get("round"), ("phase",)),
            "player_id": pick(player, ("steamid", "activity")),
            "player_state": pick(player.get("state"), ("health",))}


class AutoHide:
    """Full GSI snapshots replace state; missing/stale state fails closed."""
    def __init__(self):
        self.state = {}
        self.received = None

    def update(self, state, *, now=None):
        self.state = state
        self.received = time.monotonic() if now is None else now

    def visible(self, *, auto_hide=True, always_visible=False, now=None):
        if always_visible or not auto_hide:
            return True
        now = time.monotonic() if now is None else now
        if self.received is None or now - self.received > 15:
            return False
        s = self.state
        if s.get("map", {}).get("phase") in ("warmup", "gameover"):
            return True
        if s.get("round", {}).get("phase") in ("freezetime", "over"):
            return True
        # Spectating another alive player must not hide the local dead HUD.
        provider = s.get("provider", {}).get("steamid")
        player = s.get("player_id", {}).get("steamid")
        if provider and player and provider != player:
            return True
        return s.get("player_state", {}).get("health") == 0
