"""Pure GSI-only round card policy. Unknown, stale and spectator state hide it."""
import time
from . import MAPS, canonical


def context(game_state, settings, *, now=None):
    if not settings.get('overlay_enabled') or 'lineups' not in settings.get('overlay_tools', ()):
        return {'show': False}
    now = time.monotonic() if now is None else now
    if game_state.received is None or now-game_state.received > 15:
        return {'show': False}
    state = game_state.state
    player, provider = state.get('player_id', {}), state.get('provider', {})
    side = player.get('team')
    key = canonical(state.get('map', {}).get('name'))
    if (side not in ('T','CT') or not provider.get('steamid')
            or provider['steamid'] != player.get('steamid') or key not in MAPS
            or state.get('map', {}).get('phase') not in ('warmup','live')):
        return {'show': False}
    buying = (state.get('map', {}).get('phase') == 'warmup'
              or state.get('round', {}).get('phase') == 'freezetime')
    pinned = settings.get('overlay_layout', {}).get('lineups', {}).get('pinned', False)
    return {'map':key,'name':MAPS[key],'side':side,'buying':buying,'pinned':pinned,
            'show':pinned or (buying and settings.get('overlay_lineups_round_start',True))}
