from .base import Tool

def data(state, args=None):
    adapter = state.overlay.panel.regions
    return adapter.poll() if adapter.visible else adapter.open()

def lock(state, args):
    code = args.get('code')
    if not isinstance(code, str) or not code:
        raise ValueError('Choose a listed region')
    return state.overlay.panel.regions.request(code)

def unlock(state, args):
    return state.overlay.panel.regions.request()

TOOL = Tool('serverlock', 'Server lock', 'globe', data,
            {'lock': lock, 'unlock': unlock}, default_size=(350, 320))
