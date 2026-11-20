"""Explicit, reviewed tool registry; importing it starts no resources."""
from .performance import TOOL as PERFORMANCE
from .hardware import TOOL as HARDWARE
from .events import TOOL as EVENTS
from .profiles import TOOL as PROFILES
from .serverlock import TOOL as SERVERLOCK
from .lineups import TOOL as LINEUPS
from .settings import TOOL as SETTINGS

TOOLS = (PERFORMANCE, HARDWARE, EVENTS, PROFILES, SERVERLOCK, LINEUPS, SETTINGS)
REGISTRY = {tool.id: tool for tool in TOOLS}

def listing(state):
    import copy
    from ...cli import load_prefs
    from ... import profiles
    from ...webui import _active_account
    prefs = load_prefs()
    ui = profiles.ui_for(prefs, _active_account(state))
    return {'tools': [tool.manifest() for tool in TOOLS],
            'settings': copy.deepcopy(state.overlay._settings),
            'theme': ui.get('theme', 'violet')}

def dispatch(state, body):
    if not isinstance(body, dict):
        raise ValueError('Expected tool request object')
    tool_id = body.get('id')
    tool = REGISTRY.get(tool_id) if isinstance(tool_id, str) else None
    if tool is None:
        raise ValueError('Unknown tool')
    action = body.get('action', 'data')
    fn = tool.data if action == 'data' else tool.actions.get(action) if isinstance(action, str) else None
    if fn is None:
        raise ValueError('Unknown tool action')
    args = body.get('args', {})
    if not isinstance(args, dict):
        raise ValueError('Tool args must be an object')
    panel = state.overlay.panel
    if not panel or not panel.visible or not state.overlay.panel_allowed():
        return {'available': False, 'text': 'Panel hidden'}
    if tool.id not in state.overlay._settings['overlay_tools']:
        raise ValueError('Tool is disabled')
    return fn(state, args)
