"""Read-only, lazy Lineups adapter; dispatch gates it before any IO."""
from .base import Tool


def data(state, args=None):
    from ...lineups import MAPS, load
    from ...webui import _lineups_art
    args = args or {}
    round_state = state.overlay.lineups_state()
    key = args.get('map', round_state.get('map', 'mirage'))
    document = load(key)
    art = None
    if document:
        art = _lineups_art(state, document['map'])
    return {'maps': [{'id': k, 'name': v} for k,v in MAPS.items()],
            'document': document, 'art': art, 'round': round_state,
            'map_request': 'map' in args}


TOOL = Tool('lineups', 'Lineups', 'globe', data, refresh_hz=1,
            default_size=(900, 610), pinnable=True)
