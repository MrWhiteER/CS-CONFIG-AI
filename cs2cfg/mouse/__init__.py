"""Mouse speed (DPI) and polling rate, set straight on the mouse.

No maker software is launched or needed: each brand module writes the
mouse's own USB reports, the same way the lighting does (see cs2cfg.rgb).
Razer is first; SteelSeries and HyperX slot in as more ``Brand`` modules.
"""

from .control import DEFAULTS, MouseControl, read_settings

__all__ = ["DEFAULTS", "MouseControl", "read_settings"]
