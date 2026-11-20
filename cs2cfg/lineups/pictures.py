"""Player-triggered practice pictures; imports are inert and fake caches isolated."""
import base64
import hashlib
import html
import json
import math
import re
from pathlib import Path
from . import validate
from .radar import png

UNAVAILABLE = ('Lineup pictures are not available in this build. '
               'The app cannot confirm the practice player position and aim from game state yet. '
               'Use the radar and written steps for now.')


def request(*, enabled):
    """Fail closed, without probing the game, launching it or writing any files."""
    if not enabled:
        return {'available': False, 'text': 'Turn on the overlay and Lineups first.'}
    return {'available': False, 'text': UNAVAILABLE}


SHOTS_CFG = 'cs2cfg_lineup_shots.cfg'
UNDO_CFG = 'cs2cfg_lineup_shots_undo.cfg'
KEYS = tuple('F' + str(n) for n in range(6, 12))


def offline_ready(state):
    """An ambiguous mode is never evidence of an offline game."""
    try:
        local = state['provider']['steamid']
        player = state.get('player_id', state.get('player', {}))
        game = state['map']
        if (state['provider']['appid'] != 730 or not local
                or player.get('steamid') != local or player.get('activity') != 'playing'
                or game.get('name') != 'de_mirage'
                or game.get('mode') not in ('practice', 'offline')
                or state.get('round', {}).get('phase', game.get('phase'))
                not in ('warmup', 'freezetime', 'live')):
            return False
        players = state.get('allplayers', {})
        if not isinstance(players, dict):
            return False
        return all(identity == local or
                   (isinstance(p, dict) and p.get('bot') is True)
                   or (identity.upper().startswith('BOT') and isinstance(p, dict))
                   for identity, p in players.items())
    except (KeyError, TypeError, AttributeError):
        return False


def shot_plan(document):
    return [(row, kind) for row in document['lineups'] for kind in ('stand', 'aim')]


def capture_cfg(document, key='F8', previous=None):
    """Only the player's chosen key executes movement. No game input API."""
    if key not in KEYS:
        raise ValueError('Choose a picture key from the list.')
    # A read binding must be one plain command, never executable cfg syntax.
    if previous and not re.fullmatch(r'[+\w .-]+', previous):
        previous = None
    undo = (f'bind "{key}" "{previous}"\n' if previous else f'unbind "{key}"\n')
    undo += 'sv_cheats 0\nalias cs2cfg_picture ""\n'
    lines = ['sv_lan 1', 'sv_cheats 1']
    for index, (row, kind) in enumerate(shot_plan(document)):
        s, a = row['stand'], row['aim']
        pitch = 89 if kind == 'stand' else a['pitch']
        next_step = (f'alias cs2cfg_picture cs2cfg_picture_{index+1}'
                     if index+1 < len(shot_plan(document)) else
                     'exec cs2cfg_lineup_shots_undo')
        # Retail screenshot command not confirmed: capture follows real GSI pose.
        lines.append(f'alias cs2cfg_picture_{index} "setpos {s["x"]} {s["y"]} {s["z"]}; '
                     f'setang {pitch} {a["yaw"]} 0; {next_step}"')
    lines += ['alias cs2cfg_picture cs2cfg_picture_0', f'bind "{key}" "cs2cfg_picture"']
    return '\n'.join(lines)+'\n', undo


def read_binding(paths, key):
    """Read references only; never rewrite the player's bindings."""
    for path in paths:
        try:
            text = Path(path).read_text(encoding='utf-8')
            # CS2 key vcfg and legacy bind syntax.
            matches = re.findall(r'"'+re.escape(key)+r'"\s+"([^"\r\n]*)"', text, re.I)
            matches += re.findall(r'bind\s+"?'+re.escape(key)+r'"?\s+"([^"\r\n]*)"', text, re.I)
            if matches:
                return matches[-1]
        except (OSError, UnicodeError):
            pass
    return None


def game_build(install):
    from .. import vdf
    manifest = Path(install).parent.parent/'appmanifest_730.acf'
    build = vdf.parse(manifest.read_text(encoding='utf-8'))['AppState']['buildid']
    if not str(build).isdigit():
        raise ValueError('The game version is unavailable.')
    return str(build)


class PictureSession:
    """Event-driven external capture. All paths/backends are supplied by caller.

    No sleeps, launch deadlines, keyboard simulation or console execution.
    Startup cfg is provisional until fresh GSI proves the allowed practice mode.
    """
    def __init__(self, document, build, cache, cfg, capture, key='F8'):
        self.document = validate(document)
        self.root = Path(cache)/'lineup-pictures'/document['map']/cache_key(document, build)
        self.cfg = Path(cfg)
        self.capture = capture
        self.key = key
        self.index = 0
        self.active = False
        self.ready = False
        self.seen_game = False
        self.text = ''

    def start(self, launch, *, running=False, previous=None):
        if running:
            self.text = 'Close CS2, then press Make lineup pictures again.'
            return False
        if not self.cfg.is_dir() or any((self.cfg/name).is_symlink() for name in (SHOTS_CFG, UNDO_CFG)):
            raise OSError('The game picture setup folder is unavailable.')
        shots, undo = capture_cfg(self.document, self.key, previous)
        self.active = True
        try:
            (self.cfg/UNDO_CFG).write_text(undo, encoding='utf-8')
            (self.cfg/SHOTS_CFG).write_text(shots, encoding='utf-8')
            launch('+map de_mirage +exec cs2cfg_lineup_shots')
        except Exception:
            self.abort('The practice game could not start. Close CS2 and try again.')
            raise
        self.text = 'Waiting for Mirage practice. Keep the game visible.'
        return True

    def cleanup(self):
        for name in (SHOTS_CFG, UNDO_CFG):
            (self.cfg/name).unlink(missing_ok=True)

    def abort(self, text='Pictures stopped. Saved pictures were kept. Close CS2 before playing online.'):
        self.active = False
        self.text = text
        self.cleanup()

    def game_running(self, running):
        if not self.active:
            return
        if running:
            self.seen_game = True
        elif self.seen_game:
            self.abort()

    def feed(self, state):
        if not self.active:
            return False
        if not self.ready and not state.get("map", {}).get("name"):
            return False  # Startup/menu events cannot advance a picture.
        if not offline_ready(state):
            self.abort('Pictures stopped: offline Mirage practice could not be confirmed. '
                       'Saved pictures were kept. Close CS2 before playing online.')
            return False
        self.ready = True
        self.text = f'Picture {self.index+1} of {len(shot_plan(self.document))} - press {self.key}'
        row, kind = shot_plan(self.document)[self.index]
        expected = {**row, 'aim': {**row['aim'], 'pitch': 89 if kind == 'stand' else row['aim']['pitch']}}
        # Reuse strict pose comparison, accepting the owner's allowed phases.
        pose = {**state, 'map': {**state['map'], 'phase': 'warmup'},
                'player': {**state.get('player_id', state.get('player', {})),
                           **state.get('player', {}), 'state': state.get('player_state', state.get('player', {}).get('state', {}))}}
        if not pose_matches(self.document, expected, pose):
            if not pose['player'].get('position') or not pose['player'].get('forward'):
                self.abort('Pictures stopped: this game does not report the practice camera. '
                           'Use the radar and steps. Close CS2 before playing online.')
            return False
        try:
            frame = self.capture()
            svg = annotate(frame, kind=kind, label=row['steps'][0 if kind == 'stand' else 1],
                           point=(frame[0]//2, frame[1]//2))
            folder = self.root/str(self.index//2)
            folder.mkdir(parents=True, exist_ok=True)
            (folder/(kind+'.svg')).write_text(svg, encoding='utf-8')
        except (OSError, ValueError):
            self.text = 'Keep the practice game visible. Picture not saved yet; do not press the picture key again.'
            return False
        self.index += 1
        if self.index == len(shot_plan(self.document)):
            self.active = False
            self.cleanup()
            self.text = f'Done - {self.index} pictures saved'
        else:
            self.text = f'Picture {self.index+1} of {len(shot_plan(self.document))} - press {self.key}'
        return True


def cached_pictures(document, build, cache):
    root = Path(cache)/'lineup-pictures'/document['map']/cache_key(document, build)
    result = {}
    for index, row in enumerate(document['lineups']):
        images = {}
        for kind in ('stand', 'aim'):
            path = root/str(index)/(kind+'.svg')
            if path.is_file():
                images[kind] = 'data:image/svg+xml;base64,'+base64.b64encode(path.read_bytes()).decode('ascii')
        if images:
            result[row['id']] = images
    return result


def cache_key(document, build):
    if not isinstance(build, str) or not build.strip():
        raise ValueError('Game build required')
    data=json.dumps({'version': 1, 'build': build, 'document': validate(document)},
                    sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(data).hexdigest()


def practice_cfg(row):
    """Reviewable local-server plan only; never installed or executed by this module."""
    stand, aim = row['stand'], row['aim']
    return ('sv_lan 1\nsv_cheats 1\nbot_kick\n'
            'mp_warmup_pausetimer 1\n'
            f"setpos {stand['x']} {stand['y']} {stand['z']}\n"
            f"setang {aim['pitch']} {aim['yaw']} 0\n")


def pose_matches(document, row, state):
    """Trial readiness check on a full, authenticated GSI snapshot.

    This does NOT establish offline provenance. Do not use it to authorize
    game control. A map/warmup event without position cannot authorize a shot.
    The production parser intentionally remains unchanged while this trial is
    disconnected. GSI positions are documented for observers, not a playing
    practice client; silently treating absent values as zero would hide that.
    """
    try:
        if (state['provider']['appid'] != 730
                or state['provider']['steamid'] != state['player']['steamid']
                or not state['provider']['steamid']
                or state['map']['name'] != 'de_' + document['map']
                or state['map']['phase'] != 'warmup'
                or state['player']['activity'] != 'playing'
                or state['player']['state']['health'] <= 0):
            return False
        def vector(value):
            # GSI supplies comma-separated strings, not pixel coordinates.
            parts = tuple(float(v.strip()) for v in value.split(','))
            if len(parts) != 3 or not all(math.isfinite(v) for v in parts):
                raise ValueError('Missing practice position')
            return parts
        position = vector(state['player']['position'])
        forward = vector(state['player']['forward'])
        pitch, yaw = (math.radians(row['aim'][k]) for k in ('pitch', 'yaw'))
        expected = (math.cos(pitch)*math.cos(yaw), math.cos(pitch)*math.sin(yaw), -math.sin(pitch))
        return (math.dist(position, tuple(row['stand'][k] for k in ('x','y','z'))) <= 2
                and math.dist(forward, expected) <= 0.01)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return False


class CaptureTrial:
    """Disconnected single-shot-per-launch experiment, with fakeable frames.

    Caller must already own a verified offline launch. This class cannot
    establish that provenance, launch CS2, or close it. No production code
    instantiates it. New launches must have monotonically increasing IDs;
    snapshots from a previous launch cannot advance the next shot. There are
    no sleeps, inferred camera coordinates, or acceptance of map-only events.
    """
    def __init__(self, document, capture):
        self.document = validate(document)
        self.capture = capture
        self.index = 0
        self.launch_id = 0
        self.waiting = False
        self.frames = []

    def begin_launch(self, launch_id):
        if (self.waiting or self.index == len(self.document['lineups'])
                or not isinstance(launch_id, int) or isinstance(launch_id, bool)
                or launch_id <= self.launch_id):
            raise ValueError('A new practice launch is required')
        self.launch_id = launch_id
        self.waiting = True
        return practice_cfg(self.document['lineups'][self.index])

    def feed(self, launch_id, state):
        if not self.waiting or launch_id != self.launch_id:
            return False
        row = self.document['lineups'][self.index]
        if not pose_matches(self.document, row, state):
            return False
        frame = self.capture()
        # Validate before advancing; a failed/blank backend must be retryable.
        marked = annotate(frame, kind='aim', label=row['steps'][1],
                          point=(frame[0]//2, frame[1]//2))
        self.frames.append(marked)
        self.waiting = False
        self.index += 1
        return True


def annotate(frame, *, kind, label, point):
    """Mark a supplied frame: the real stand camera looks down at 89 degrees."""
    width, height, rgba = frame
    x,y = point
    if (kind not in ('aim','stand') or not 1 <= width <= 4096 or not 1 <= height <= 4096
            or len(rgba) != width*height*4 or not 0 <= x < width or not 0 <= y < height):
        raise ValueError('Invalid picture')
    image=base64.b64encode(png(width,height,rgba)).decode('ascii')
    ink='#ffff00'
    marker=(f'<circle cx="{x}" cy="{y}" r="18" fill="none" stroke="{ink}" stroke-width="5"/>'
            if kind == 'aim' else
            f'<path d="M{x+40} {y-50} L{x} {y} M{x} {y} l4 -18 M{x} {y} l18 -4" '
            f'fill="none" stroke="{ink}" stroke-width="5"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">'
            f'<image width="{width}" height="{height}" href="data:image/png;base64,{image}"/>'
            +marker+f'<rect x="0" y="0" width="{width}" height="30" fill="#111"/>'
            f'<text x="10" y="21" fill="{ink}" font-family="sans-serif" font-size="14">'
            +html.escape(label[:72])+'</text></svg>')


class DryRun:
    """Event-driven fake runner. Fake readiness is never accepted as real GSI.

    feed() advances only on the expected map, phase and shot identity. There
    are no timers. This exercises sequencing, not real CS2 synchronization.
    """
    def __init__(self, document, build, cache):
        self.document=validate(document)
        self.key=cache_key(document,build)
        self.root=Path(cache)/'lineup-pictures-dry-run'/document['map']/self.key
        self.index=0
        self.complete=False

    def feed(self, event):
        if self.complete:
            return False
        rows=self.document['lineups']
        row=rows[self.index]
        if (event.get('fake') is not True or event.get('map') != self.document['map']
                or event.get('phase') != 'warmup' or event.get('shot') != row['id']):
            return False
        # Sequential filenames avoid treating data identities as paths.
        folder=self.root/str(self.index)
        folder.mkdir(parents=True,exist_ok=True)
        (folder/'practice.cfg.txt').write_text(practice_cfg(row),encoding='utf-8')
        for kind, step in [('stand',0),('aim',1)]:
            marked=annotate(event['frames'][kind],kind=kind,
                            label='TEST PICTURE: '+row['steps'][step],
                            point=event['points'][kind])
            (folder/(kind+'.svg')).write_text(marked,encoding='utf-8')
        self.index+=1
        if self.index == len(rows):
            target=self.root/'complete.json'
            temp=target.with_suffix('.tmp')
            temp.write_text(json.dumps({'fake':True,'key':self.key,'count':len(rows)}),encoding='utf-8')
            temp.replace(target)
            self.complete=True
        return True


def dry_run(document, build, cache):
    runner=DryRun(document,build,cache)
    frame=(640,360,bytes([32,40,56,255])*640*360)
    for row in document['lineups']:
        runner.feed({'fake':True,'map':document['map'],'phase':'warmup','shot':row['id'],
                     'frames':{'stand':frame,'aim':frame},
                     'points':{'stand':(320,260),'aim':(320,180)}})
    return runner.root
