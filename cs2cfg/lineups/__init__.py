"""Read-only lineup data. Importing this package performs no file IO."""
import copy
import json
import math
import re
from functools import lru_cache
from ..paths import bundle_root

TYPES = {'smoke': 'Smoke', 'fire': 'Fire', 'flash': 'Flash', 'grenade': 'Grenade'}
THROWS = ('left click', 'right click', 'both', 'jump throw', 'run throw', 'walk throw')
MAPS = {'mirage': 'Mirage', 'inferno': 'Inferno', 'nuke': 'Nuke', 'ancient': 'Ancient',
        'anubis': 'Anubis', 'dust2': 'Dust II', 'overpass': 'Overpass'}


def canonical(value):
    return str(value or '').removeprefix('de_')


def plain(value):
    return (isinstance(value, str) and 0 < len(value) <= 240
            and not re.search(r'de_|setpos|setang|smokegrenade|molotov|[<>\x00-\x1f]', value, re.I))


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate(document):
    """Reject incomplete records, hidden command text and points outside the overview."""
    if not isinstance(document, dict) or document.get('map') not in MAPS or not plain(document.get('name')):
        raise ValueError('Invalid map')
    o = document.get('overview')
    if not isinstance(o, dict) or not isinstance(document.get('lineups'),list):
        raise ValueError('Invalid lineup data')
    if not all(number(o.get(k)) for k in ('pos_x', 'pos_y', 'scale', 'width', 'height')):
        raise ValueError('Invalid overview')
    if o['scale'] <= 0 or not 1 <= o['width'] <= 4096 or not 1 <= o['height'] <= 4096:
        raise ValueError('Invalid overview size')
    seen = set()
    for row in document['lineups']:
        required = {'id','name','side','type','area','stand','aim','throw','land','steps','source','checked'}
        if not isinstance(row,dict) or not required <= row.keys():
            raise ValueError('Incomplete lineup')
        if not isinstance(row.get('id'), str) or row['id'] in seen or not row['id']:
            raise ValueError('Invalid lineup identity')
        seen.add(row['id'])
        if (not plain(row.get('name')) or row.get('side') not in ('T', 'CT', 'both')
                or row.get('type') not in TYPES or (not plain(row.get('area')) if row.get('mine') is True else row.get('area') not in ('A', 'B', 'Mid'))
                or row.get('throw') not in THROWS or not isinstance(row.get('checked'), bool)
                or row.get('source') not in ('CS2-annotations, MIT', 'own')):
            raise ValueError('Invalid lineup')
        if not isinstance(row.get('steps'), list) or not 1 <= len(row['steps']) <= (30 if row.get('mine') is True else 3) or not all(map(plain, row['steps'])):
            raise ValueError('Invalid instructions')
        normalized = [re.sub(r'[^a-z0-9]+', ' ', step.casefold()).strip() for step in row['steps']]
        if len(set(normalized)) != len(normalized):
            raise ValueError('Repeated instructions')
        landmarks = ('t spawn', 'ct spawn', 'palace', 'ramp', 'connector', 'jungle',
                     'ticket', 'stairs', 'mid', 'short', 'market', 'apartments', 'bench', 'van')
        if row.get('mine') is not True and document['map'] == 'mirage' and any(
                'marked point' in step or not any(place in step for place in landmarks)
                for step in normalized):
            raise ValueError('Instructions need a Mirage landmark')
        a = row['aim']
        if not (row.get('mine') is True and a is None) and (not isinstance(a,dict) or not all(number(a.get(k)) for k in ('pitch', 'yaw')) or not -90 <= a['pitch'] <= 90 or not -180 <= a['yaw'] <= 180):
            raise ValueError(f"Invalid aim for lineup {row['id']} ({row['name']})")
        for key in ('stand', 'land'):
            point = row[key]
            if row.get('mine') is True:
                if key == 'land' and point is None:
                    continue
                if isinstance(point, dict) and set(point) == {'radar_x', 'radar_y'}:
                    if (not all(number(point[k]) for k in point)
                            or not 0 <= point['radar_x'] <= o['width']
                            or not 0 <= point['radar_y'] <= o['height']):
                        raise ValueError('Point outside overview')
                    continue
            if (not isinstance(point,dict) or any(k in point for k in ('radar_x', 'radar_y'))
                    or not all(number(point.get(k)) for k in ('x', 'y', 'z'))):
                raise ValueError('Invalid point')
            x, y = pixel(point, o)
            if not 0 <= x <= o['width'] or not 0 <= y <= o['height']:
                raise ValueError('Point outside overview')
    return document


def pixel(point, overview):
    if 'radar_x' in point:
        return point['radar_x'], point['radar_y']
    return ((point['x'] - overview['pos_x']) / overview['scale'],
            (overview['pos_y'] - point['y']) / overview['scale'])


@lru_cache(maxsize=16)
def _load(key):
    return validate(json.loads((bundle_root() / 'lineups/data' / f'{key}.json').read_text(encoding='utf-8')))


def load(map_key='mirage'):
    key = canonical(map_key)
    if key != 'mirage':  # More map data is step 5; empty maps need no file reads.
        return None
    return copy.deepcopy(_load(key))


def search(rows, query='', side='', kind=''):
    synonyms = {'molly': 'fire', 'molotov': 'fire', 'incendiary': 'fire',
                'nade': 'grenade', 'he': 'grenade', 'pop': 'flash'}
    words = [synonyms.get(w, w) for w in re.findall(r'\w+', query.casefold()) if w != 'site']
    return [r for r in rows if (not side or r['side'] in (side, 'both'))
            and (not kind or (r.get('mine') is True if kind == 'mine' else r['type'] == kind))
            and all(w in f"{r['name']} {r['area']} {r['type']}".casefold() for w in words)]
