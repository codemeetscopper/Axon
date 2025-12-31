from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def encode_command(command: Dict[str, Any]) -> str:
    return json.dumps(command, separators=(",", ":"))


def decode_line(line: str) -> Dict[str, Any] | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def prepare_init_commands(commands: Iterable[Dict[str, Any]]) -> List[str]:
    return [encode_command(cmd) for cmd in commands]
