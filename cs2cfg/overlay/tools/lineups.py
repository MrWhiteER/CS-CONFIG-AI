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
    images = {}
    if document and state.cs2_install:
        from ...lineups.pictures import game_build, cached_pictures
        from ...paths import user_data_dir
        try:
            images = cached_pictures(document, game_build(state.cs2_install), user_data_dir())
        except (OSError, ValueError, KeyError):
            pass
    session = state.overlay.picture_session
    return {'maps': [{'id': k, 'name': v} for k,v in MAPS.items()],
            'document': document, 'art': art, 'round': round_state,
            'map_request': 'map' in args, 'pictures': images,
            'picture_status': session.text if session else ''}


TOOL = Tool('lineups', 'Lineups', 'globe', data, refresh_hz=1,
            default_size=(1000, 620), pinnable=True)
