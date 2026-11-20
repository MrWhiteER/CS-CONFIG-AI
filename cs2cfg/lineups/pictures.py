"""Picture preparation prototype. No production game control or capture backend.

Importing this module does no work. Fake output is isolated from real caches.
The brief permits radar-only fallback when safe capture cannot be implemented.
"""
import base64
import hashlib
import html
import json
from pathlib import Path
from . import validate
from .radar import png

UNAVAILABLE = ('Lineup pictures are not available in this build. '
               'The app cannot safely move the practice camera and confirm each shot yet. '
               'Use the radar and written steps for now.')


def request(*, enabled):
    """Fail closed, without probing the game, launching it or writing any files."""
    if not enabled:
        return {'available': False, 'text': 'Turn on the overlay and Lineups first.'}
    return {'available': False, 'text': UNAVAILABLE}


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


def annotate(frame, *, kind, label, point):
    """Overlay on a supplied frame. Caller must supply a calibrated pixel point.

    No stand marker is guessed from the crosshair: looking straight ahead does
    not locate the player's feet in a stand picture. Fake tests supply this.
    """
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
