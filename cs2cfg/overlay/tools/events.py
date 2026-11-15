from .base import Tool

def data(state, args=None):
    return {'events': state.overlay.snapshot(1)['events']}

TOOL = Tool('events', 'Stutters and freezes', 'pulse', data, default_size=(430, 280))
