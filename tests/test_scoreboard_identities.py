"""Roster decoration stays independent of the numeric scoreboard and demo."""
import io
import json
from unittest import mock

import pytest

from cs2cfg import demos, webui

MATCH = "1-12345678-1234-1234-1234-123456789abc"


def roster():
    return {"teams": {"faction1": {
        "name": "team_owner", "avatar": "https://cdn/team.png",
        "roster": [{"id": "p1", "nickname": "owner", "avatar": "https://cdn/p.png",
                    "gameSkillLevel": "10"},
                   {"player_id": "p2", "nickname": "other", "game_skill_level": 7}]
    }}}


@pytest.mark.parametrize("wrapped", [True, False])
def test_match_roster_carries_player_and_team_identity(wrapped):
    body = {"payload": roster()} if wrapped else roster()
    calls = []
    def get(url):
        calls.append(url)
        return io.BytesIO(json.dumps(body).encode())
    result = demos.identities(MATCH, opener=get)
    assert calls == [demos.MATCH_API.format(match_id=MATCH)]
    team = result["teams"][0]
    assert team["avatar"] == "https://cdn/team.png"
    assert team["players"][0] == {"player_id": "p1", "nickname": "owner",
                                  "avatar": "https://cdn/p.png", "level": 10}
    assert team["players"][1]["level"] == 7
    assert team["players"][1]["avatar"] == ""


def test_unknown_levels_remain_unknown():
    body = roster()
    body["teams"]["faction1"]["roster"][0]["gameSkillLevel"] = 42
    result = demos.identities(MATCH, opener=lambda _: io.BytesIO(json.dumps(body).encode()))
    assert result["teams"][0]["players"][0]["level"] == 0


@pytest.mark.parametrize("body", [b'not json', b'null', b'{}', b'{"teams":null}'])
def test_unavailable_decoration_is_nonfatal(body):
    assert demos.identities(MATCH, opener=lambda _: io.BytesIO(body))["teams"] == []


def test_cache_and_network_failure_are_bounded():
    with mock.patch.dict(demos._identity_cache, clear=True), \
         mock.patch.object(demos, "_open", side_effect=OSError("offline")) as get:
        assert demos.identities(MATCH)["teams"] == []
        assert demos.identities(MATCH)["teams"] == []
        get.assert_called_once_with(demos.MATCH_API.format(match_id=MATCH), timeout=5)


def test_success_cache_expires():
    with mock.patch.dict(demos._identity_cache, clear=True), \
         mock.patch.object(demos.time, "monotonic", side_effect=[0, 1, 3602, 3602]), \
         mock.patch.object(demos, "_open", side_effect=lambda *a, **k: io.BytesIO(json.dumps(roster()).encode())) as get:
        demos.identities(MATCH)
        demos.identities(MATCH)
        demos.identities(MATCH)
        assert get.call_count == 2


def test_endpoint_is_additive_and_rejects_bad_links():
    assert webui._demo_identities(None, {"link": "bad"})["ok"] is False
    with mock.patch.object(demos, "identities", return_value={"teams": []}):
        assert webui._demo_identities(None, {"link": MATCH}) == {"ok": True, "teams": []}


def test_bad_link_never_reaches_faceit():
    with mock.patch.object(demos, "_open") as get:
        with pytest.raises(demos.DemoError):
            demos.identities("bad")
        get.assert_not_called()
