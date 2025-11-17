"""Definitions for the OSI layers used to organize runtime components."""

from __future__ import annotations

from enum import Enum, auto


class OsiLayer(Enum):
    """Subset of the OSI model relevant to the Axon runtime."""

    PHYSICAL = auto()
    DATA_LINK = auto()
    NETWORK = auto()
    TRANSPORT = auto()
    SESSION = auto()
    PRESENTATION = auto()
    APPLICATION = auto()
