"""Personal lineups. No IO until an enabled tool calls this module."""
import copy
import json
import threading
import uuid
from . import MAPS, canonical, load, validate
from ..paths import user_data_dir

_lock = threading.RLock()


def _path(key):
    key = canonical(key)
    if key not in MAPS:
        raise ValueError('Choose a map from the list.')
    return user_data_dir() / 'lineups' / 'mine' / (key + '.json')


def personal(key):
    path = _path(key)
    try:
        doc = validate(json.loads(path.read_text(encoding='utf-8')))
        if doc['map'] != canonical(key) or any(r.get('mine') is not True for r in doc['lineups']):
            raise ValueError('Personal lineup data is unavailable.')
        return doc
    except FileNotFoundError:
        return None


def combined(key):
    with _lock:
        seed, mine = load(key), personal(key)
        if not mine:
            return seed
        result = copy.deepcopy(seed or mine)
        result['lineups'] = (seed['lineups'] if seed else []) + mine['lineups']
        return validate(result)


def _write(doc):
    validate(doc)
    path = _path(doc['map'])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def save(key, row, overview=None):
    with _lock:
        mine = personal(key)
        seed = load(key)
        if mine is None:
            mine = {'map': canonical(key), 'name': MAPS[canonical(key)],
                    'overview': copy.deepcopy((seed or {}).get('overview') or overview), 'lineups': []}
        row = copy.deepcopy(row)
        identity = row.get('id')
        if identity and not any(r['id'] == identity for r in mine['lineups']):
            raise ValueError('This lineup is no longer available.')
        row.update(id=identity or 'mine-' + uuid.uuid4().hex, mine=True, source='own', checked=False)
        mine['lineups'] = [r for r in mine['lineups'] if r['id'] != row['id']] + [row]
        _write(mine)
        return row


def delete(key, identity):
    with _lock:
        mine = personal(key)
        row = next((r for r in (mine or {}).get('lineups', []) if r['id'] == identity), None)
        if row is None:
            raise ValueError('This lineup is no longer available.')
        mine['lineups'].remove(row)
        _write(mine)
        return row


def restore(key, row):
    with _lock:
        mine = personal(key)
        if mine is None or any(r['id'] == row['id'] for r in mine['lineups']):
            raise ValueError('This lineup cannot be restored.')
        mine['lineups'].append(copy.deepcopy(row))
        _write(mine)
