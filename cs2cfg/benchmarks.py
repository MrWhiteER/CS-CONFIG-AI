"""Label and compare measured sessions without inventing performance results."""
from __future__ import annotations

import json
import math
import statistics
import time
from . import fileio
from .paths import user_data_dir


def _path():
    return user_data_dir() / 'benchmarks.json'


def load():
    try:
        data = json.loads(_path().read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fileio.write_text(path, json.dumps(data, indent=1))


def arm(slot, map_id, context):
    if slot not in ('A', 'B'):
        raise ValueError('Choose benchmark run A or B.')
    map_id = str(map_id or '').strip()[:80]
    if not map_id:
        raise ValueError('Label the map or repeatable workload first.')
    with fileio.LOCK:
        data = load()
        data['armed'] = {'slot': slot, 'map': map_id, 'context': context, 'at': time.time()}
        _save(data)
    return data['armed']


def claim(meta):
    with fileio.LOCK:
        data = load()
        armed = data.pop('armed', None)
        if not armed:
            return {}
        _save(data)
        return {**armed, 'preset': meta.get('intent'), 'resolution': meta.get('resolution'),
                'map_source': 'player workload label'}


def compare(sessions, left, right):
    if not isinstance(left, list) or not isinstance(right, list) or not left or not right:
        raise ValueError('Select at least one recorded run for A and B.')
    if set(left) & set(right):
        raise ValueError('A run cannot be on both sides of the comparison.')
    by_id = {str(s.get('stamp')): s for s in sessions}
    warnings = []

    def group(ids):
        rows = []
        for identity in ids[:12]:
            if identity not in by_id:
                raise ValueError('A selected session is no longer available. Reload the runs.')
            s = by_id[identity]
            metrics = s.get('overlay') or {}
            fps = metrics.get('avg_fps')
            if not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0 or (s.get('duration') or 0) < 120 or (metrics.get('frame_count') or 0) < 1000:
                raise ValueError('Each run needs at least 120 seconds and 1,000 captured frames. Enable frame capture and repeat the workload.')
            rows.append(s)
        def median(key):
            values = [float((s.get('overlay') or {}).get(key)) for s in rows if isinstance((s.get('overlay') or {}).get(key), (int,float)) and math.isfinite((s.get('overlay') or {})[key])]
            return round(statistics.median(values),2) if values else None
        fps_values = [s['overlay']['avg_fps'] for s in rows]
        return rows, {'runs':len(rows), 'avg_fps':median('avg_fps'), 'one_percent_low':median('one_percent_low'),
                      'avg_frame_time_ms':round(1000/statistics.median(fps_values),3),
                      'worst_frame_ms':median('worst_frame_ms'),
                      'fps_range':[round(min(fps_values),2),round(max(fps_values),2)]}

    a, am = group(list(dict.fromkeys(left)))
    b, bm = group(list(dict.fromkeys(right)))
    all_rows = a+b
    for field in ('resolution','map','context'):
        values = [(s.get('benchmark') or {}).get(field) if field != 'resolution' else s.get('resolution') for s in all_rows]
        if field=='context':
            values=[{k:v for k,v in (value or {}).items() if k!='preset'} for value in values]
        if any(not v for v in values):
            warnings.append(f'{field.capitalize()} was not recorded for every run.')
        elif any(v != values[0] for v in values[1:]):
            warnings.append(f'{field.capitalize()} differs; results are not a controlled comparison.')
    if len(a)<3 or len(b)<3:
        warnings.append('Use at least three runs per preset to understand run-to-run variation.')
    warnings.append('Workload labels are supplied by the player. Matching labels do not prove identical gameplay.')
    return {'A': am, 'B': bm, 'fps_change_percent': round((bm['avg_fps']/am['avg_fps']-1)*100,2),
            'warnings':warnings, 'left':left, 'right':right, 'at':time.time()}


def remember(result):
    with fileio.LOCK:
        data=load()
        data['comparisons']=(data.get('comparisons') or [])[-19:]+[result]
        _save(data)
