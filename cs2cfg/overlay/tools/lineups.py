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
    from ...lineups.creating import pictures
    from ...paths import user_data_dir
    from ...lineups.creating import builtin_metadata
    metadata = builtin_metadata(document['map'], user_data_dir()) if document else {}
    for row in (document or {}).get('lineups', []):
        if not row.get('mine') and row['id'] in metadata:
            row['pictures'] = metadata[row['id']]
        own = pictures(row, user_data_dir())
        if own:
            images[row['id']] = own
    session = state.overlay.picture_session
    return {'maps': [{'id': k, 'name': v} for k,v in MAPS.items()],
            'document': document, 'art': art, 'round': round_state,
            'map_request': 'map' in args, 'pictures': images,
            'picture_status': session.text if session else '',
            'picture_active': bool(session and session.active),
            'position': player_position(state),
            'position_notice': position_notice(state),
            'creating': state.overlay.creating_session.snapshot() if getattr(state.overlay, 'creating_session', None) else None,
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


def position_notice(state):
    from ...lineups.window_capture import process_started
    written = getattr(state.overlay, '_gsi_written_at', None)
    started = process_started(getattr(state.overlay, '_hwnd', None))
    if written is not None and started is not None and written > started:
        return 'Restart CS2 once so the game can share your position.'
    return 'The game has not shared your position yet. Move a step and press again.'


def editing(state, args=None):
    with state.overlay._lock:
        state.overlay.lineups_editing = bool((args or {}).get('active'))
        state.overlay._configure_gsi(state.overlay._settings['overlay_enabled'])
    return data(state, args)


def creating(state, args=None):
    from ...lineups.creating import CreatingSession
    from ...lineups.window_capture import capture_cs2
    from ..hud import Hud
    overlay = state.overlay
    args = args or {}
    action = args.get('action', 'start')
    if action == 'cancel':
        overlay.cancel_creating()
        return {'active': False, 'text': ''}
    if not overlay._settings['overlay_enabled'] or 'lineups' not in overlay._settings['overlay_tools']:
        return {'active': False, 'text': 'Turn on the overlay and Lineups first.'}
    if action == 'status':
        return overlay.creating_session.snapshot() if overlay.creating_session else {}
    try:
        if action != 'retake':
            overlay.cancel_creating()
            overlay.creating_session = CreatingSession(capture_cs2,
                overlay._settings['overlay_lineups_create_key'], changed=overlay.picture_changed)
        session = overlay.creating_session
        if args.get('builtin'):
            from ...lineups import load
            from ...lineups.pictures import pose_matches
            document = load(args.get('map'))
            row = next((r for r in (document or {}).get('lineups', []) if r['id'] == args['builtin']), None)
            if not row:
                raise ValueError('Choose a lineup.')
            def checked_capture():
                game = overlay._game_state
                expected = {**row, 'aim': {**row['aim'], 'pitch': 89 if session.waiting == 'stand' else row['aim']['pitch']}}
                pose = player_position(state)
                snapshot = {**game.state, 'map': {**game.state.get('map', {}), 'phase': 'warmup'},
                            'player': {**game.state.get('player', {}), 'state': game.state.get('player_state', {})}}
                if pose and session.waiting == 'stand':
                    expected['aim'] = pose['aim']
                if not pose or not pose_matches(document, expected, snapshot):
                    raise ValueError('Follow the stand and aim instructions before taking this picture.')
                return capture_cs2()
            session.capture = checked_capture
        if not session:
            raise ValueError('Take pictures first.')
        if not overlay._picture_widget:
            widget = Hud(exclude_from_capture=True, register_hotkeys=False)
            widget.tool = 'picture'
            overlay._picture_widget = widget
            widget.start()
        session.wait(args.get('kind', 'stand'))
        # Close the native panel immediately; capture never relies on a fade timer.
        if overlay.panel:
            overlay.panel.hide()
            if overlay.panel.window:
                overlay.panel.window.hide()
        return session.snapshot()
    except (OSError, ValueError, RuntimeError) as exc:
        overlay.cancel_creating()
        return {'active': False, 'text': str(exc) if isinstance(exc, ValueError) or str(exc).startswith('The picture key') else 'Pictures could not start. Keep CS2 visible and try again.'}


PLAIN_ERRORS = {'Take pictures first.', 'Take both pictures first.', 'Choose a larger crop.',
                'Choose a crop inside the picture.', 'Place the picture marker.', 'This lineup is no longer available.'}


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
        elif action == 'save_pictures':
            from ...lineups.creating import save_builtin
            from ...paths import user_data_dir
            session = getattr(state.overlay, 'creating_session', None)
            if not session:
                raise ValueError('Take pictures first.')
            metadata = session.save(args.get('picture_edits') or {}, user_data_dir())
            save_builtin(key, args.get('row', {}).get('id'), metadata, user_data_dir())
            state.overlay.cancel_creating()
        elif action == 'save':
            row = dict(args.get('row', {}))
            session = getattr(state.overlay, 'creating_session', None)
            if args.get('picture_edits') is not None:
                from ...paths import user_data_dir
                if not session:
                    raise ValueError('Take pictures first.')
                row['pictures'] = session.save(args['picture_edits'], user_data_dir())
            mine.save(key, row, args.get('overview'))
            state.overlay.cancel_creating()
        else:
            raise ValueError('Choose a lineup action.')
        state.overlay.lineups_notice = ''
    except ValueError as exc:
        state.overlay.lineups_notice = 'Could not save your change. ' + (str(exc) if str(exc) in PLAIN_ERRORS else 'Check the fields and try again.')
    except Exception:
        import logging
        logging.getLogger(__name__).exception('lineup change failed')
        state.overlay.lineups_notice = 'Could not save your change. Check the fields and try again.'
    result = data(state, {'map': key})
    result['undo_available'] = bool(getattr(state.overlay, 'lineups_undo', None))
    return result


TOOL = Tool('lineups', 'Lineups', 'globe', data, refresh_hz=1,
            actions={'stop_pictures': stop_pictures, 'change': change, 'editing': editing, 'creating': creating},
            default_size=(1000, 620), pinnable=True)
