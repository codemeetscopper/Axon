from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from axon_chassis_service.main import run_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Axon chassis bridge (simulation socket).")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("/home/pi/axon_chassis_service/config/axon_bridge_sim.yaml"),
        help="Path to axon_bridge_sim.yaml",
    )
    args = parser.parse_args()
    asyncio.run(run_service(args.config))


if __name__ == "__main__":
    main()
