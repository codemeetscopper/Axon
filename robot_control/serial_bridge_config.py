"""Configuration dataclass for the TCP serial bridge."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SerialBridgeConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    welcome_message: str = "Axon serial bridge ready\n"
    encoding: str = "utf-8"
