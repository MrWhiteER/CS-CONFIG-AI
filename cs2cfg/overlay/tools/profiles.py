from .base import Tool

def data(state, args=None):
    from ...webui import _setups, _cfg_layouts_profiles
    return {'setups': _setups(state, {}), 'layouts': _cfg_layouts_profiles(state, {})}

def setup(state, args):
    from ...webui import _setups_act
    return _setups_act(state, {'do': 'use', 'name': args.get('name')})

def layout(state, args):
    from ...webui import _cfg_layouts_apply
    return _cfg_layouts_apply(state, {'file': args.get('file')})

TOOL = Tool('profiles', 'Profiles', 'layers', data,
            {'setup': setup, 'layout': layout}, refresh_hz=0, default_size=(350, 330), pinnable=True)
