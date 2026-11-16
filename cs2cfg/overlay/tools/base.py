"""Explicit tool contract; construction starts no resources."""
from dataclasses import dataclass, field
from typing import Callable

@dataclass(frozen=True)
class Tool:
    id: str
    title: str
    icon: str
    data: Callable
    actions: dict = field(default_factory=dict)
    refresh_hz: float = 1
    default_size: tuple = (420, 320)
    pinnable: bool = False

    def manifest(self):
        return {k: getattr(self, k) for k in
                ('id', 'title', 'icon', 'refresh_hz', 'default_size', 'pinnable')}
