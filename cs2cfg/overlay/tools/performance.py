from .base import Tool

def data(state, args=None):
    snapshot = state.overlay.snapshot(600)
    return {k: snapshot[k] for k in ('current', 'summary', 'history',
        'frame_capture_ready', 'frame_capture_hint', 'frame_capture_hint_dismissible',
        'notice', 'error', 'hud_warning', 'panel_warning', 'game_running')}

def dismiss(state, args):
    from ...webui import _overlay_settings
    return _overlay_settings(state, {'overlay_sign_out_hint_dismissed': True})

TOOL = Tool('performance', 'Performance', 'activity', data,
            {'dismiss': dismiss}, default_size=(510, 390), pinnable=True)
