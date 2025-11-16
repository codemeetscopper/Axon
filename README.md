# Robotic Face Widget

This project provides a fully featured robotic face widget built with PySide6. The widget presents a cute, expressive face for an AI robot display and exposes a simple API for integrating emotion and orientation controls.

## Features

- Smooth animations between a wide range of emotions (happy, sad, surprised, sleepy, curious, neutral, excited).
- Dark-themed design with vibrant accents and subtle 3D lighting.
- Rich API for updating the current emotion and the robot's yaw/pitch/roll orientation.
- Idle breathing motion, blinking, and eye sparkle animations to keep the face feeling alive.
- Designed for a 640x800 landscape screen (automatically scales to fit).

## Getting Started

### Prerequisites

- Python 3.9+
- [PySide6](https://pypi.org/project/PySide6/)

Install dependencies with:

```bash
pip install -r requirements.txt
```

### Running the demo

```bash
python simulation_main.py
```

Use the control panel to experiment with different emotions and orientation values. The new **Robot link** card (default host
`192.168.1.169`) lets you tether the desktop face to a live robot: once connected the simulator streams telemetry from the TCP
bridge, drives the embedded face with real motion data, and disables the manual sliders so you can focus on remote monitoring.

### Robot runtime and TCP bridge

To drive the face from real telemetry, launch the hardware runtime:

```bash
python robot_main.py
```

The runtime now exposes a TCP server on port 8765 that echoes every command it receives, forwards it to the robot's serial bus, and streams the latest telemetry frame to every connected client. This makes it easy to issue manual serial writes and monitor the sensor feed from another computer on the same network.

Launch the rich PySide6 client to connect to the bridge from another laptop:

```bash
python serial_command_client.py --host <robot-ip> --port 8765
```

The client shares the same reusable TCP connection helper as the simulator, shows a live telemetry dashboard, a scrollback log (including the raw frames coming off the robot), and a command composer with send/clear controls. Any commands typed into the bottom bar are echoed back by the runtime so you can confirm they reached the robot.

### Robot runtime and TCP bridge

To drive the face from real telemetry, launch the hardware runtime:

```bash
python robot_main.py
```

The runtime now exposes a TCP server on port 8765 that echoes every command it receives, forwards it to the robot's serial bus, and streams the latest telemetry frame to every connected client. This makes it easy to issue manual serial writes and monitor the sensor feed from another computer on the same network.

Launch the rich PySide6 client to connect to the bridge:

```bash
python serial_command_client.py --host <robot-ip> --port 8765
```

The client shows a live telemetry dashboard, a scrollback log (including the raw frames coming off the robot), and a command composer with send/clear controls. Any commands typed into the bottom bar are echoed back by the runtime so you can confirm they reached the robot.

## Integrating the Widget

Import and instantiate `RoboticFaceWidget` in your PySide6 project:

```python
from axon_ui import RoboticFaceWidget

face = RoboticFaceWidget()
face.set_emotion("happy")
face.set_orientation(yaw=10, pitch=-5, roll=2)
```

The widget is self-contained and can be embedded into any existing layout or window.

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.
