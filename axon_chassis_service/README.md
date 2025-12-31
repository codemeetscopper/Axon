# Axon Chassis Service

Production-ready Raspberry Pi bridge service for a Waveshare Wave Rover chassis.

## Features

- Asyncio-based serial + TCP bridge using line-delimited JSON.
- Single serial writer queue, auto-reconnect, and init commands on reconnect.
- Multi-client TCP server with persistent sessions and keepalive ping/pong.
- Watchdog safety stop when control commands go stale.
- Interface-driven design for future ROS 2 integration (stubs included, no ROS deps).

## Installation

```bash
sudo apt-get update
sudo apt-get install -y python3-venv
python3 -m venv /home/pi/axon_chassis_service/venv
source /home/pi/axon_chassis_service/venv/bin/activate
pip install -r /home/pi/axon_chassis_service/requirements.txt
```

Copy the service directory to the Raspberry Pi:

```bash
sudo rsync -av ./axon_chassis_service/ /home/pi/axon_chassis_service/
```

## Configuration

Edit `/home/pi/axon_chassis_service/config/axon_bridge.yaml` to match your serial port and network settings.

## Running Manually

```bash
source /home/pi/axon_chassis_service/venv/bin/activate
python -m axon_chassis_service.main --config /home/pi/axon_chassis_service/config/axon_bridge.yaml
```

## TCP Protocol

Line-delimited JSON messages over TCP.

### Client -> Server

- **Command** (direct payload):

```json
{"T":1,"L":0.2,"R":0.2}
```

- **Command** (wrapped):

```json
{"type":"command","data":{"T":1,"L":0.2,"R":0.2}}
```

- **Subscribe / Unsubscribe**:

```json
{"type":"subscribe","feedback":true}
```

- **Ping / Pong** (client may send; server also pings):

```json
{"type":"ping"}
```

### Server -> Client

- **Feedback**: raw JSON line received from serial.
- **Keepalive**:

```json
{"type":"ping"}
```

## Testing with netcat

```bash
nc 127.0.0.1 9000
```

Send a command:

```json
{"T":1,"L":0.3,"R":0.3}
```

## Python Client Example

```python
import asyncio
import json

async def main():
    reader, writer = await asyncio.open_connection("127.0.0.1", 9000)
    writer.write((json.dumps({"T": 1, "L": 0.2, "R": 0.2}) + "\n").encode())
    await writer.drain()
    while True:
        line = await reader.readline()
        if not line:
            break
        print(line.decode().strip())

asyncio.run(main())
```

## Serial Mock (No Hardware Needed)

A PySide6 GUI mock is included for OS-independent testing without a physical serial port.

1) Install the mock requirements:

```bash
pip install -r /home/pi/axon_chassis_service/requirements-mock.txt
```

2) Run the mock server:

```bash
python /home/pi/axon_chassis_service/tools/serial_mock.py
```

3) Point the bridge to the mock using a socket URL in `axon_bridge.yaml`:

```yaml
serial:
  port: socket://127.0.0.1:7000
```

The mock implements the Wave Rover command set basics:
- `{"T":1,"L":0.5,"R":0.5}` speed control
- `{"T":11,"L":164,"R":164}` PWM control
- `{"T":3,"lineNum":0,"Text":"hello"}` OLED line
- `{"T":-3}` OLED reset
- `{"T":130}` one-shot feedback
- `{"T":131,"cmd":1}` enable continuous feedback
- `{"T":143,"cmd":1}` enable echo

## Systemd Service

Copy the unit file and enable it:

```bash
sudo cp /home/pi/axon_chassis_service/systemd/axon-chassis.service /etc/systemd/system/axon-chassis.service
sudo systemctl daemon-reload
sudo systemctl enable axon-chassis.service
sudo systemctl start axon-chassis.service
sudo journalctl -u axon-chassis.service -f
```

## ROS 2 Integration (Future)

`axon_chassis_service/ros_adapter_stub.py` contains placeholder classes that implement the same interfaces as the core system. Replace those stubs with ROS 2 adapters later without touching the core logic.
