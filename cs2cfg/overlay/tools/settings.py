from .base import Tool

def data(state, args=None):
    return {'settings': state.overlay.snapshot(1)['settings']}

def save(state, args):
    from ...webui import _overlay_settings
    return _overlay_settings(state, args)

TOOL = Tool('settings', 'Settings', 'settings', data, {'save': save},
            refresh_hz=0, default_size=(700, 650))
