"""What every mouse brand offers the app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Reading:
    """One mouse as the app found it. Plain words only; shown as they are."""

    id: str                         # stable within this PC: brand + product id
    name: str                       # "Razer Cobra HyperSpeed"
    connection: str = ""            # "wireless" / "cable" / ""
    dpi: Optional[int] = None       # what the mouse uses now, if it said
    poll: Optional[int] = None      # reports a second, if it said
    min_dpi: int = 100
    max_dpi: int = 20000
    dpi_step: int = 50
    rates: Tuple[int, ...] = ()     # polling rates it takes; () = can't set
    tested: bool = True             # model checked on a real mouse
    problem: str = ""               # why something could not be read or set

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "connection": self.connection,
                "dpi": self.dpi, "poll": self.poll, "min_dpi": self.min_dpi,
                "max_dpi": self.max_dpi, "dpi_step": self.dpi_step,
                "rates": list(self.rates), "tested": self.tested,
                "problem": self.problem}


class Brand:
    """One maker's mice.

    ``find`` lists mice and reads what each one uses now; it changes nothing.
    ``set`` writes a speed and/or polling rate to one mouse and returns what
    the mouse says afterwards. Neither starts or needs the maker's software.
    """

    name = ""

    def find(self) -> List[Reading]:
        raise NotImplementedError

    def set(self, mouse_id: str, dpi: Optional[int] = None,
            poll: Optional[int] = None) -> Reading:
        raise NotImplementedError

