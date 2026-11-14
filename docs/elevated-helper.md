# The one-time administrator helper

Edy's rule: the app asks for every permission **once**, during setup, and never shows an administrator prompt again. That covers app start, fixes, launches, the region lock and the overlay.

## How it works

1. **Setup (one UAC prompt).** On the first-run permission step, `POST /api/helper/install` runs `cs2cfg/helper/install.ps1` elevated. It does five things:
   - copies `broker.ps1` to `C:\Program Files\CS CONFIG AI Helper\`, where only admins can change it;
   - creates `C:\ProgramData\CS CONFIG AI Helper\{requests,claimed,results}`, where this user can write `requests` and read `results`, and only admins can do anything else;
   - registers the scheduled task `\CS CONFIG AI\Helper`, which runs on demand with highest privileges as this user, and is hidden;
   - adds the user to **Performance Log Users** (S-1-5-32-559) so the overlay can read performance counters without admin; this takes effect at the next Windows sign-in;
   - grants the user Modify on this PC's CS2 cfg folder.
2. **Every time after that (no prompt).** The app writes `requests/<id>.json` with `{op, args}`, runs `schtasks /run /tn "\CS CONFIG AI\Helper"`, and reads `results/<id>.json`.

## Python API (`cs2cfg/elevated.py`)

```python
from cs2cfg import elevated

elevated.ready()                  # helper installed and current
elevated.status()                 # {supported, installed, current, version, wanted}
elevated.run(op, args, timeout=45, wait=True)
#   -> the broker's answer dict, always with "ok"
#   -> {"ok": False, "needs_setup": True, ...} if setup never installed it
#   never raises, never prompts
```

When `run` answers `needs_setup`, fall back to your old path, or send the user to Settings → "Run setup again".

## The jobs (the only things it will ever do)

| op | args | does |
|---|---|---|
| `ping` | none | `{ok, version}` |
| `firewall.lock` | `{program: <full path to ...\game\bin\win64\cs2.exe>, regions: [{name, cidrs: ["a.b.c.d/nn", ...]}]}` | Replaces all the helper's lock rules with one **outbound block** rule per region, for cs2.exe only, in the firewall group `CS CONFIG AI region lock`. Allows 1–64 regions and up to 2000 IPv4 CIDRs (/8–/32). Names must match `[A-Za-z0-9 _-.()]{1,48}`. |
| `firewall.unlock` | none | removes every rule in that group (and nothing else) |
| `firewall.status` | none | `{ok, blocked: [region names]}` |
| `dns.flush` | none | flushes the DNS cache |
| `adapter.restart` | `{name}` | restarts a physical adapter, which must exist |
| `audio.restart` | none | restarts Windows Audio |
| `device.restart` | `{instance_id}` | Disables then re-enables a peripheral (Mouse, Keyboard, HIDClass, AudioEndpoint, Media, USB, Bluetooth, Image). It never touches the last mouse or keyboard. |
| `power.set` | `{guid}` | switches to an existing power plan |
| `cfg.grant` | `{path: ...\steamapps\common\<x>\game\csgo\cfg}` | makes that folder writable for this user |
| `temps.watch` | `{pid}` | publishes board and drive temperatures to `results/temps.json` until that process exits (max 12 h); use `wait=False` |
| `faceit_ac.start` | none | starts FACEIT Anti-Cheat from the path in its own HKLM uninstall entry, never from a request |
| `defender.cs2` | `{program: cs2.exe path, on: bool}` | adds or removes a Defender exclusion for CS2's own install folder only |

**Adding a job:**
1. Add it to `$Jobs` in `broker.ps1` and to `OPS` and `validate()` in `elevated.py`.
2. Bump `$Version` and `HELPER_VERSION`.
3. Add a test.

Bumping the version means each PC sees **one** more prompt to put the new helper in place. So batch new jobs together and keep the list stable.

## Safety lines (keep them)

- No job runs a command, script or program named in a request. No `Invoke-Expression`; a test checks for this.
- Every argument is checked twice: once in Python and again in the broker.
- Requests that are links, too large, or have bad ids are deleted unread. Request content is never echoed back.
- The firewall work only ever adds block rules for cs2.exe, and only removes rules from its own group.
- The Defender toggle on/off in Fix It stays limited to CS2's folder.
- Uninstall with `elevated.remove()` (one prompt). It removes the task, the rules, and both folders.

## What still prompts, and why

- **Setup itself:** once.
- **A helper version bump:** once per bump, as described above.
- **A PC where setup was skipped:** every fix still works, with the old one-off prompt, until the user runs setup.
- **The app itself never runs elevated.** The installer is per-user (`PrivilegesRequired=lowest`) and the exe has no admin manifest. The app must stay unelevated, because launching CS2 through `steam://` from an elevated process would start Steam elevated.
