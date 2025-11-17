# Axon Runtime Suite

Axon is the complete runtime for the expressive robotic face experience. The
codebase includes the face widget, motion-to-emotion control stack, simulator,
robot runtime, and TCP bridge so laptops can drive hardware remotely. This
README describes how the major pieces fit together and how to run them.

## Repository layout

| Path | Purpose |
|------|---------|
| `axon_ui/` | Robotic face widget, overlays, palettes, and TCP bridge client. |
| `axon_ros/` | Runtime wrappers and OSI-inspired instrumentation used by the simulator and robot entry points. |
| `robot_control/` | Sensor ingest, calibration, emotion policy, face controller, and serial/TCP bridge utilities. |
| `robot_main.py` | Fullscreen robot runtime that binds the serial reader, controller, telemetry overlays, and TCP bridge. |
| `simulation_main.py` | Desktop simulator that generates sensor samples for testing the UI/logic stack. |
| `misc/` | Command-line helpers such as the remote UI client and serial CLI tools. |
| `docs/` | Architecture notes and workflow documentation for the full Axon stack. |

## Features

- PySide6 face widget with smooth emotions, idle animations, and orientation
  support.
- Hardware-ready runtime that reads `SensorSample` frames from a UART bridge,
  auto-calibrates the gyro, and streams telemetry to the UI.
- TCP serial bridge (`SerialBridgeServer`) that mirrors telemetry and forwards
  operator commands to the robot.
- Desktop simulator with the same overlays for rapid iteration without hardware.
- Lightweight ROS2-inspired layout (see `axon_ros`) for describing the moving
  pieces via OSI layers.

## Prerequisites

- Python 3.9+
- System dependencies required by PySide6/Qt

Install Python dependencies with:

```bash
pip install -r requirements.txt
```

## Running the simulator

```bash
python simulation_main.py [--bridge-host 192.168.1.42] [--bridge-port 8765]
```

The simulator boots the `SimulatorMainWindow`, creates a `RoboticFaceWidget`,
and exposes tabs for emotion presets, telemetry inspection, and remote bridge
configuration. Use this mode to validate the control stack without hardware.

## Running on the robot

```bash
python robot_main.py
```

The robot runtime waits for the serial hardware to settle, opens the UART port,
and starts the `SerialBridgeServer`. `RobotRuntime` continuously polls the
serial reader, feeds samples through the `GyroCalibrator`, applies the
`EmotionPolicy` via `FaceController`, and updates the fullscreen
`RobotMainWindow`. Telemetry and info overlays stay synchronized with the UI.

## Remote UI over TCP

A laptop can connect to the robot's TCP bridge and render the face UI locally
without a direct serial connection. Use the helper in `misc/remote_ui_main.py`:

```bash
python misc/remote_ui_main.py --host 192.168.1.169 --port 8765
```

The bridge streams lines that originate on the serial bus and accepts commands.
See `misc/serial_command_client.py` for a headless example.

## Documentation

The [`docs/`](docs) folder contains a detailed architecture overview and a
step-by-step workflow description that mirrors the current code. Consult those
documents when modifying the data flow, adding nodes, or integrating new
hardware sources.

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for
complete details.
