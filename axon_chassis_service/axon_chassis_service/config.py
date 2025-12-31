from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from .models import LoggingConfig, NetworkConfig, SerialConfig, ServiceConfig, WatchdogConfig


DEFAULT_CONFIG_PATH = Path("/home/pi/axon_chassis_service/config/axon_bridge.yaml")


def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path | None = None) -> ServiceConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return ServiceConfig()

    data = yaml.safe_load(config_path.read_text()) or {}

    serial_data = data.get("serial", {})
    network_data = data.get("network", {})
    watchdog_data = data.get("watchdog", {})
    logging_data = data.get("logging", {})

    serial = SerialConfig(**_merge(SerialConfig().__dict__, serial_data))
    network = NetworkConfig(**_merge(NetworkConfig().__dict__, network_data))
    watchdog = WatchdogConfig(**_merge(WatchdogConfig().__dict__, watchdog_data))
    logging = LoggingConfig(**_merge(LoggingConfig().__dict__, logging_data))

    return ServiceConfig(serial=serial, network=network, watchdog=watchdog, logging=logging)
