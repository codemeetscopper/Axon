from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class SerialConfig:
    port: str = "/dev/ttyUSB0"
    baudrate: int = 115200
    reconnect_delay_s: float = 2.0
    read_timeout_s: float = 0.5
    init_commands: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class NetworkConfig:
    host: str = "0.0.0.0"
    port: int = 9000
    ping_interval_s: float = 5.0
    ping_timeout_s: float = 15.0
    max_clients: int = 16


@dataclass(frozen=True)
class WatchdogConfig:
    timeout_s: float = 0.5
    stop_command: Dict[str, Any] = field(default_factory=lambda: {"T": 1, "L": 0.0, "R": 0.0})


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    json: bool = True


@dataclass(frozen=True)
class ServiceConfig:
    serial: SerialConfig = field(default_factory=SerialConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
