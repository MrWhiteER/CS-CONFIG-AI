# Server ping drop-up: brief for Codex

Edy plays from Dubai. Lately CS2's Dubai servers are down or bad, and every match (Premier,
Competitive, Deathmatch) puts him on 80+ ping even though his in-game max matchmaking ping is
set under 30 ms. He wants to see, from inside the app, **which CS2 server regions he can reach
right now and what his ping to each one is**.

You (Codex) own the design, icons, animation and engineering. This brief gives you the data,
where it goes and the constraints.

---

## 1. Where it goes

The Play tab hero, `#home-hero` in `cs2cfg/web/index.html` (markup around line 5743, CSS around
line 5336). Edy marked the **bottom-right corner** of the hero, over the artwork (the chair
area, to the right of the soldier). It must sit on top of the hero art without covering the
Play button column on the left.

- **Closed state:** a compact pill/chip anchored bottom-right. It shows a server-status icon,
  the best region right now and its ping (e.g. `DUBAI  · 18 ms`), coloured by quality. A small
  live pulse shows it is measuring. If Edy's preferred region is degraded or down, the pill says
  so (e.g. `DUBAI DOWN · best: MUMBAI 41 ms`).
- **Open state: a drop-UP.** Clicking the pill opens a panel that grows **upward** from it (it
  must not be clipped by `overflow:hidden` on `.home-hero`; raise it or portal it). Inside:
  - A **search box** at the top that filters by **country** (and city), e.g. typing `india`
    shows Mumbai and Chennai, `emirates` or `uae` shows Dubai. Match on the region's country
    name, city name and the short code (`dxb`).
  - A scrollable list of regions, sorted by ping (best first; unreachable at the bottom).
    Each row: country flag or region icon, city, country, a **ping bar** and the number in ms,
    and a status icon (good / ok / bad / down).
  - Colour is a **continuous gradient from green to red** by ping, not three flat buckets.
    Suggested stops: <= 30 ms green, 60 ms yellow-green, 90 ms amber, 130 ms orange, >= 180 ms
    red. Unreachable / 100% loss is a muted grey row with a "down" icon.
  - A marker on the bars at Edy's **max matchmaking ping** if you can read it (see 3.4), so it
    is obvious which regions are inside his limit.
  - A refresh button and "updated N s ago".
  - Esc, clicking outside or clicking the pill closes it. Keyboard: arrow keys move through the
    rows, typing goes to the search box.

## 2. Icons and animation (Edy asked for these specifically)

Design an original icon set for server status, inline SVG, 1.5 to 2 px stroke like the rest of
the app, colour from tokens:

- **Good / OK / Bad / Down** status glyphs (e.g. signal bars or a server rack with a status LED;
  "down" gets a cross or broken link).
- **Measuring**: an animated sweep / radar or bars filling in while a region is being pinged.
- **Live pulse** on the closed pill while results are fresh.
- Rows **stagger in** when the drop-up opens (slide up + fade, 30 to 40 ms apart).
- Ping numbers **tween** to new values on refresh, and bars animate their width; the colour
  follows the value along the gradient.
- The drop-up **unfolds upward** (transform-origin bottom, scale/translate + opacity).

Respect the existing rules: transform and opacity only, 60 fps, pause when the window is
hidden (`visibilitychange`), honour `prefers-reduced-motion`. All 10 themes must still look
right; pull neutrals from tokens. The green-to-red ping gradient is a data scale and may use
`--good` / `--warn` / `--bad` blended with `color-mix()` so it follows the theme.

## 3. Getting the real ping (backend)

### 3.1 The list of regions: Valve's SDR config

CS2 matchmaking runs over Valve's Steam Datagram Relay (SDR). Valve publishes the list of
points of presence (POPs) and their relay addresses, unauthenticated:

```
GET https://api.steampowered.com/ISteamApps/GetSDRConfig/v1/?appid=730
```

Shape (abridged):

```json
{ "revision": 1731500000,
  "pops": {
    "dxb": { "desc": "Dubai (United Arab Emirates)", "geo": [55.36, 25.25], "tier": 1,
             "relays": [ { "ipv4": "155.133.x.x", "port_range": [27015, 27060] }, ... ] },
    "bom2": { "desc": "Mumbai (India)", ... },
    ...
  } }
```

- `desc` is `"City (Country)"`; split it for the search (city + country).
- Skip POPs that have no `relays` (partner/internal-only entries) and anything whose `desc` is
  missing.
- Some POPs are numbered variants (`bom`, `bom2`, `sto`, `sto2`); group them under one city and
  show the best ping.
- Cache the response on disk (e.g. next to the app's other caches) and refresh at most once a
  day. Ship a small bundled fallback list so the widget works offline and on the first run.
- I could not fetch the endpoint from my sandbox (network blocked), so verify the exact field
  names on Edy's PC before relying on them.

### 3.2 Measuring

- Ping each POP's relay IPs from Edy's PC. The app already does ICMP ping through `ping.exe`
  in `cs2cfg/netcheck.py` (`_ping_once`, hidden window via `_hidden()`, localised `time=` parsing).
  Reuse that rather than writing a second parser.
- Most SDR relays answer ICMP. If a relay never answers ICMP, try a second relay for that POP;
  if none answer, mark the region **unknown**, not "down", unless Valve's config itself is
  unreachable. (Optional, better: Steam's own relay ping is UDP on the `port_range`; only do this
  if you can confirm the packet format, do not guess it.)
- 3 to 5 probes per POP, take the median; report loss too. Run POPs in parallel with a thread
  pool (about 8 workers) so the whole sweep finishes in a few seconds.
- The number shown is ping **to the relay**, which is what CS2 uses to pick a datacenter. Say
  so in a tooltip: "Ping to Valve's relay in this city. In-game ping is usually within a few ms."
- Do **not** run continuously in the background. Measure when the Play tab is shown (if the last
  result is older than about 60 s), when the drop-up opens, and on the refresh button. It is real
  network traffic; the existing `/api/net/start` has the same rule.

### 3.3 API

Follow the pattern of `/api/net/start` + `/api/net` in `cs2cfg/webui.py` (around line 2594 and
the route table near line 4299):

- `POST /api/servers/ping/start` starts a sweep and returns immediately.
- `GET /api/servers/ping` returns progress plus per-region results:
  `{ running, updated_at, regions: [{ code, city, country, ping_ms, loss, status, relays_tried }] }`.
- Put the logic in a new module, e.g. `cs2cfg/serverping.py`, with unit tests in
  `tests/test_serverping.py` (parse the SDR JSON, group numbered POPs, pick the median, classify
  status, the colour stop for a ping). Mock `ping.exe`; tests must not touch the network.

### 3.4 Edy's max ping (optional, nice to have)

CS2 keeps the "Max acceptable matchmaking ping" in the cvar `mm_dedicated_search_maxping`, saved
in the user's `cs2_user_convars_0_slot0.vcfg` under
`Steam\userdata\<id>\730\local\cfg\`. The app already finds that folder for other features. If
you can read it, draw the limit as a marker on the bars and dim regions above it. If not, leave
the marker out.

## 4. Rules

1. Don't change existing element ids, `data-*` attributes or API behaviour. New ids are fine.
2. No CDNs, no external images. Flags: draw them or use a compact inline set; regional-indicator
   emoji flags don't render on Windows, so don't rely on them.
3. Keep the tests passing (`python -m pytest`, or the normal runner on Edy's PC).
4. Work on branch `codex/ping-widget` from `main`. Commit and push it. **Don't open a PR and don't
   publish a release**: Edy previews it first, and releases only happen when Edy types GUPDATE.

## 5. Verified on Edy's PC (2026-11-13)

- `GET https://api.steampowered.com/ISteamApps/GetSDRConfig/v1/?appid=730` works with no key.
  Top-level keys: `revision, pops, certs, p2p_share_ip, relay_public_key, revoked_keys,
  typical_pings, success` (`success: true`, revision 1794268433).
- `pops` is an object keyed by POP code: **53 pops**, 45 of them with a `relays` list. The 8
  without relays (`ctu, eat, fsn, hel, pek, pvg, tgd, dsto`) can't be pinged; skip or grey them.
- Dubai is present:
  `"dxb": {"desc": "Dubai (United Arab Emirates)", "geo": [55.3, 25.25], "partners": 1, "tier": 0,
  "relays": [{"ipv4": "185.25.183.163", "port_range": [27015, 27060]},
  {"ipv4": "185.25.183.179", "port_range": [27015, 27060]}]}`. Note `geo` is `[lon, lat]`.
- `typical_pings` is a list of 195 `[popA, popB, ms]` triples (e.g. `["ams", "dfra", 6]`).
- ICMP to relays is answered: `ping -n 2 185.25.183.163` (dxb) → 125 / 141 ms, 0% loss;
  `ping -n 2 155.133.226.68` (fra) → 110 / 109 ms, 0% loss. So plain ICMP ping of a relay ipv4 is
  a valid measurement method on this PC.
