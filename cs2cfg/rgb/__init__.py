"""Keyboard and mouse RGB that follows the keyboard tab's binding colours.

See sync.py for the loop, palette.py for the colour rule, and one module per
lighting API (chroma, gamesense, openrgb).
"""

from .sync import DEFAULTS, RgbSync, read_settings

__all__ = ["DEFAULTS", "RgbSync", "read_settings"]
