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

Use the control panel to experiment with different emotions and orientation values.

### ROS2-inspired runtime layout

The runtime has been reorganized to mirror a ROS2 workspace. The new `axon_ros`
package exposes dedicated "nodes" for the simulator (`SimulatorMainWindow`), the
robot runtime (`RobotRuntime`/`RobotMainWindow`), and the shared UI overlay
(`FaceTelemetryDisplay`). Each class lives in its own module so individual nodes
can be composed from launch files or standalone scripts.

### Robot runtime + serial bridge

```bash
python robot_main.py
```

`robot_main.py` remains the entry-point on the robot. It now boots a
`SerialBridgeServer` that streams telemetry and forwards commands over TCP so a
laptop can drive the UI remotely. By default the bridge listens on
`0.0.0.0:8765`.

### Remote PySide6 UI (laptop)

```bash
python remote_ui_main.py --host 192.168.1.169 --port 8765
```

The remote UI connects to the robot's serial bridge (default IP
`192.168.1.169`) and mirrors the telemetry overlay plus face animations in a
windowed experience.

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
