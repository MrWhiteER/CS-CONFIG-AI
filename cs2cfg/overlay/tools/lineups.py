"""Lazy Lineups browser and picture stop action; dispatch gates all IO."""
from .base import Tool


def data(state, args=None):
    from ...lineups import MAPS, load as seed_load
    from ...lineups.mine import combined as load
    from ...webui import _lineups_art
    args = args or {}
    round_state = state.overlay.lineups_state()
    key = args.get('map', round_state.get('map', 'mirage'))
    document = load(key)
    art = None
    art = _lineups_art(state, key)
    images = {}
    if document and state.cs2_install:
        from ...lineups.pictures import game_build, cached_pictures
        from ...paths import user_data_dir
        try:
            seed = seed_load(document['map'])
            if seed:
                images = cached_pictures(seed, game_build(state.cs2_install), user_data_dir())
        except (OSError, ValueError, KeyError):
            pass
    session = state.overlay.picture_session
    return {'maps': [{'id': k, 'name': v} for k,v in MAPS.items()],
            'document': document, 'art': art, 'round': round_state,
            'map_request': 'map' in args, 'pictures': images,
            'picture_status': session.text if session else '',
            'picture_active': bool(session and session.active),
            'position': player_position(state),
            'undo_available': bool(getattr(state.overlay, 'lineups_undo', None)),
            'notice': getattr(state.overlay, 'lineups_notice', '')}


def stop_pictures(state, args=None):
    from ...webui import _lineups_pictures
    _lineups_pictures(state, {'action': 'stop'})
    return data(state)


def player_position(state):
    import math
    import time
    from ...lineups import number
    with state.overlay._lock:
        game = state.overlay._game_state
        if game.received is None or time.monotonic() - game.received > 15:
            return None
        snapshot = game.state
        player = snapshot.get('player', {})
        if (snapshot.get('provider', {}).get('appid') != 730
                or player.get('activity') != 'playing'
                or not snapshot.get('provider', {}).get('steamid')
                or player.get('steamid') != snapshot['provider']['steamid']):
            return None
        try:
            def vector(value):
                values = [float(v.strip()) for v in value.split(',')]
                if len(values) != 3 or not all(number(v) for v in values):
                    raise ValueError('Missing position')
                return values
            xyz = vector(player['position'])
            x, y, z = vector(player['forward'])
            if math.hypot(x, y) == 0 and z == 0:
                return None
            return {'stand': dict(zip(('x', 'y', 'z'), xyz)),
                    'aim': {'pitch': math.degrees(math.atan2(-z, math.hypot(x, y))),
                            'yaw': math.degrees(math.atan2(y, x))},
                    'map': snapshot.get('map', {}).get('name', '').removeprefix('de_')}
        except (KeyError, ValueError, TypeError, AttributeError):
            return None


def editing(state, args=None):
    with state.overlay._lock:
        state.overlay.lineups_editing = bool((args or {}).get('active'))
        state.overlay._configure_gsi(state.overlay._settings['overlay_enabled'])
    return data(state, args)


def creating(state, args=None):
    # No verified key/HUD acknowledgement is available through our GSI path.
    # Do not create binds, launch a game or capture on an unrelated heartbeat.
    return {'available': False, 'active': False,
            'text': 'Automatic pictures are unavailable: this app cannot verify when '
                    'the picture key has hidden the display. Save your lineup with radar '
                    'markers for now. Clean pictures would require offline practice.'}


def change(state, args=None):
    from ...lineups import mine
    args = args or {}
    key = args.get('map', 'mirage')
    try:
        action = args.get('action')
        if action == 'delete':
            row = mine.delete(key, args.get('id'))
            state.overlay.lineups_undo = (key, row)
        elif action == 'undo':
            saved = getattr(state.overlay, 'lineups_undo', None)
            if saved:
                mine.restore(*saved)
                state.overlay.lineups_undo = None
        elif action == 'save':
            mine.save(key, args.get('row', {}), args.get('overview'))
        else:
            raise ValueError('Choose a lineup action.')
        state.overlay.lineups_notice = ''
    except (ValueError, OSError, TypeError, KeyError):
        state.overlay.lineups_notice = 'Could not save your change. Check the fields and try again.'
    result = data(state, {'map': key})
    result['undo_available'] = bool(getattr(state.overlay, 'lineups_undo', None))
    return result


TOOL = Tool('lineups', 'Lineups', 'globe', data, refresh_hz=1,
            actions={'stop_pictures': stop_pictures, 'change': change, 'editing': editing, 'creating': creating},
            default_size=(1000, 620), pinnable=True)
