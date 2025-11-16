#!/usr/bin/env python3
"""Simple CLI for interacting with the Axon serial TCP bridge."""

from __future__ import annotations

import argparse
import socket
import sys
from typing import Iterable

DEFAULT_HOST = "192.168.1.169"
DEFAULT_PORT = 8765


def _send_command(sock: socket.socket, command: str) -> None:
    payload = command.strip() + "\n"
    sock.sendall(payload.encode("utf-8"))
    response = sock.recv(4096)
    if response:
        sys.stdout.write(response.decode("utf-8", errors="ignore"))
        if not response.endswith(b"\n"):
            sys.stdout.write("\n")
    sys.stdout.flush()


def _interactive_loop(sock: socket.socket) -> None:
    for line in sys.stdin:
        command = line.strip()
        if not command:
            continue
        _send_command(sock, command)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commands", nargs="*", help="Commands to send once connected")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Hostname or IP of the robot")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port exposed by the robot")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        with socket.create_connection((args.host, args.port), timeout=5.0) as sock:
            sock.settimeout(2.0)
            try:
                banner = sock.recv(1024)
                if banner:
                    sys.stdout.write(banner.decode("utf-8", errors="ignore"))
            except socket.timeout:
                pass
            if args.commands:
                _send_command(sock, " ".join(args.commands))
            else:
                print("Connected. Type commands and press Enter (Ctrl+D to quit).", flush=True)
                _interactive_loop(sock)
    except OSError as exc:
        print(f"Failed to connect: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
