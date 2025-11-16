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

## Integrating the Widget

Import and instantiate `RoboticFaceWidget` in your PySide6 project:

```python
from robotic_face_widget import RoboticFaceWidget

face = RoboticFaceWidget()
face.set_emotion("happy")
face.set_orientation(yaw=10, pitch=-5, roll=2)
```

The widget is self-contained and can be embedded into any existing layout or window.

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.
