from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from .command_arbiter import CommandArbiter
from .config import load_config
from .feedback_sinks import FanoutSink, NullSink, TcpBroadcastSink
from .logging_setup import setup_logging
from .serial_transport import SerialTransport
from .tcp_server import TcpServer


logger = logging.getLogger(__name__)


async def run_service(config_path: Path | None) -> None:
    config = load_config(config_path)
    setup_logging(config.logging.level, config.logging.json)

    tcp_server: TcpServer | None = None
    serial_transport: SerialTransport | None = None

    async def send_to_serial(command: dict) -> None:
        if serial_transport is None:
            return
        await serial_transport.send_command(command)

    arbiter = CommandArbiter(
        command_sink=send_to_serial,
        watchdog_timeout_s=config.watchdog.timeout_s,
        stop_command=config.watchdog.stop_command,
    )

    tcp_server = TcpServer(
        host=config.network.host,
        port=config.network.port,
        max_clients=config.network.max_clients,
        ping_interval_s=config.network.ping_interval_s,
        ping_timeout_s=config.network.ping_timeout_s,
        command_handler=arbiter.submit_command,
    )

    feedback_sink = FanoutSink(
        [
            TcpBroadcastSink(tcp_server),
            NullSink(),
        ]
    )

    serial_transport = SerialTransport(
        port=config.serial.port,
        baudrate=config.serial.baudrate,
        reconnect_delay_s=config.serial.reconnect_delay_s,
        read_timeout_s=config.serial.read_timeout_s,
        init_commands=config.serial.init_commands,
        feedback_sink=feedback_sink,
    )

    await arbiter.start()
    await tcp_server.start()
    await serial_transport.start()

    logger.info("Axon chassis service started")
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    try:
        import signal

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
    except (ImportError, NotImplementedError):
        logger.warning("Signal handlers unavailable; running without OS signal support")

    await stop_event.wait()

    logger.info("Shutting down Axon chassis service")
    await serial_transport.stop()
    await tcp_server.stop()
    await arbiter.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Axon chassis bridge service")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to axon_bridge.yaml (default: /home/pi/axon_chassis_service/config/axon_bridge.yaml)",
    )
    args = parser.parse_args()
    asyncio.run(run_service(args.config))


if __name__ == "__main__":
    main()
