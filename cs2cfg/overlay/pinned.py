"""Pure, read-only native widget models. No window or WebView is needed."""
from functools import lru_cache
from ..paths import bundle_root
import math
import re
import textwrap
import zlib

TITLES = {'performance': 'Performance', 'hardware': 'Hardware',
          'events': 'Stutters and freezes', 'profiles': 'Profiles', 'serverlock': 'Server lock',
          'lineups': 'Smokes for this round'}


def render(tool, data, fields=None):
    """Return bounded text and a mini graph; stable values suppress redraws."""
    def number(key, suffix='', source=None):
        value = (data if source is None else source).get(key)
        return f'{value:.1f}{suffix}' if isinstance(value, (int, float)) and math.isfinite(value) else '\u2014'

    from .settings import FIELDS
    fields = set(FIELDS if fields is None else fields)
    graph = ()
    lines = [TITLES[tool]]
    if tool == 'performance':
        current = data.get('current') or {}
        if current.get('frame_capture_ready') is False or data.get('frame_capture_ready') is False:
            current = {}
        metrics = [f"{label} {number(key, source=current)}" for key, label in
                   [('fps', 'FPS'), ('one_percent_low', '1% low')] if key in fields]
        if metrics:
            lines.append('    '.join(metrics))
        if 'frame_time_ms' in fields:
            lines.append(f"Frame {number('frame_time_ms', ' ms', current)}")
        if current:
            graph = tuple(round(max(0, min(1000, s['frame_time_ms'])), 1)
                          for s in data.get('history', [])[-60:]
                          if isinstance(s.get('frame_time_ms'), (int, float)) and math.isfinite(s['frame_time_ms']))
    elif tool == 'hardware':
        loads = [f"{label} {number(key, '%')}" for key, label in
                 [('cpu_percent', 'CPU'), ('gpu_percent', 'GPU')] if key in fields]
        if loads:
            lines.append('    '.join(loads))
        if 'gpu_temp_c' in fields:
            lines.append(f"CPU {number('cpu_temp_c', ' C')}    GPU {number('gpu_temp_c', ' C')}")
        for label, key in [('VRAM', 'vram'), ('RAM', 'ram')]:
            if data.get(key + '_used_mb') is not None:
                lines.append(f"{label} {number(key + '_used_mb')} / {number(key + '_total_mb')} MB")
    elif tool == 'events':
        for event in data.get('events', [])[:4]:
            label = 'Freeze' if event.get('type') == 'not_responding' else 'Stutter'
            stamp = event.get('at')
            # Event timestamps stay fixed, so unchanged events cause no redraw.
            from datetime import datetime
            at = datetime.fromtimestamp(stamp).strftime('%H:%M:%S') if isinstance(stamp, (int, float)) else ''
            lines.append(f"{at}   {label}   {number('duration_ms', ' ms', event)}")
        if len(lines) == 1:
            lines.append('No recent events')
    elif tool == 'profiles':
        lines += ['Setup: ' + str(data.get('setup') or 'Default'),
                  'Layout: ' + str(data.get('layout') or 'Default')]
    elif tool == 'serverlock':
        lines.append(str(data.get('text') or 'Coming soon'))
    elif tool == 'lineups':
        if data.get('picture_status'):
            lines.append(data['picture_status'])
        round_state = data.get('round', {})
        lines.append(str(round_state.get('name','')) + ' · ' + str(round_state.get('side','')) + ' side')
        names = [f"{i}. {r['name']}" for i,r in enumerate(data.get('rows', []),1)]
        lines += [', '.join(names[i:i+2]) for i in range(0,len(names),2)] if names else ['No smokes for this side yet']
        lines.append('Ctrl+Alt+P: browse and pin')
    wrapped = [part for line in lines for part in (textwrap.wrap(str(line), width=42) or [''])]
    model = {'lines': tuple(wrapped[:10 if tool == 'lineups' else 5]), 'graph': graph}
    if tool == 'lineups' and data.get('art'):
        from ..lineups.native import bitmap
        import json
        try:
            model['raster'] = bitmap(json.dumps(data['art'],sort_keys=True),
                                     json.dumps(data.get('rows',[]),sort_keys=True))
        except (ValueError, KeyError, zlib.error):
            pass
    return model


@lru_cache(maxsize=16)
def palette(theme='violet'):
    """Read the same exported app tokens as the shell, once per theme."""
    css = (bundle_root() / 'web/assets/overlay/themes.css').read_text(encoding='utf-8')
    tokens = {}
    for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        if selector.strip() == ':root' or f'[data-theme="{theme}"]' in selector:
            tokens.update(dict(re.findall(r'--([\w-]+):\s*([^;]+);', body)))
    def rgb(key, fallback):
        value = tokens.get(key, fallback).strip()
        if value.startswith('rgba('):
            return tuple(int(v.strip()) for v in value[5:-1].split(',')[:3])
        value = value.lstrip('#')
        return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))
    return rgb('panel', '#161616'), rgb('ink', '#eeeeee'), rgb('accent', '#b9a2ff')


def composite(mask, opacity=60, colors=None):
    """GDI white foreground / dark outline mask -> premultiplied BGRA.

    GDI destroys alpha. Rebuild it from the mask, keeping every glyph/line
    opaque while only the background follows the user's opacity setting.
    """
    background, ink, accent = colors or palette()
    outline = (255, 255, 255) if sum(ink) < 384 else (12, 12, 12)
    alpha = round(max(0, min(100, opacity)) * 255 / 100)
    base = bytes(round(c * alpha / 255) for c in reversed(background)) + bytes([alpha])
    result = bytearray(base * (len(mask) // 4))
    for i in range(0, len(mask), 4):
        b, g, r = mask[i:i+3]
        if r or g or b:
            color = ink if r > 128 else accent if g > 128 else outline
            result[i:i+4] = bytes((*reversed(color), 255))
    return result
