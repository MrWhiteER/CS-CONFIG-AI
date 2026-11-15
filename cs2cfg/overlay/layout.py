"""Bounded machine-wide layout. Arbitrary tool identifiers are rejected."""
import math

IDS = ('performance', 'hardware', 'events', 'profiles', 'serverlock', 'settings')

def validate(value):
    if not isinstance(value, dict) or any(k not in IDS for k in value):
        raise ValueError('Invalid overlay layout')
    out = {}
    for key, entry in value.items():
        if not isinstance(entry, dict):
            raise ValueError('Invalid tool layout')
        row = {}
        for name in ('x', 'y', 'width', 'height'):
            if name in entry:
                n = entry[name]
                if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n):
                    raise ValueError('Invalid layout coordinate')
                minimum = 0 if name in ('x', 'y') else 180 if name == 'height' else 240
                row[name] = max(minimum, min(16384, round(n)))
        for name in ('open', 'pinned'):
            if name in entry:
                if not isinstance(entry[name], bool):
                    raise ValueError('Invalid layout flag')
                row[name] = entry[name]
        if row.get('pinned') and key not in ('performance', 'hardware'):
            raise ValueError('Tool has no native pinned renderer')
        out[key] = row
    return out
