from .base import Tool

def data(state, args=None):
    current = state.overlay.snapshot(1).get('current') or {}
    return {key: current.get(key) for key in ('cpu_percent', 'gpu_percent',
        'gpu_temp_c', 'vram_used_mb', 'vram_total_mb', 'ram_used_mb', 'ram_total_mb')}

TOOL = Tool('hardware', 'Hardware', 'cpu', data, default_size=(330, 420), pinnable=True)
