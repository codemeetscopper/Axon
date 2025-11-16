# Axon Runtime Architecture

This document summarizes how the simulator and on-robot runtime collaborate to drive
the expressive face UI, gather telemetry, and expose system controls.

## High-level flow

The following diagram outlines the end-to-end data flow from the physical sensors
(or simulated sensor generator) through the calibration, emotion inference, and
UI layers.

```mermaid
flowchart LR
    subgraph Hardware/Sim
        S[Serial sensors\n(IMU, battery, misc)]
        Sim[simulation_main\nmock sample generator]
    end

    subgraph robot_control
        SR[SerialReader\n(robot_control.serial_reader)]
        GC[GyroCalibrator\n(robot_control.gyro_calibrator)]
        SD[SensorSample dataclass\n(robot_control.sensor_data)]
        FC[FaceController\n(robot_control.face_controller)]
        EP[EmotionPolicy\n(robot_control.emotion_policy)]
    end

    subgraph UI
        Face[RoboticFaceWidget]
        Display[FaceTelemetryDisplay\n(simulation_main)]
        Telemetry[TelemetryPanel\n(telemetry_panel)]
        Info[InfoPanel\n(telemetry_panel)]
    end

    S -->|UART| SR
    Sim --> SR
    SR -->|SensorSample| GC
    SR -->|raw sample| Telemetry
    GC -->|calibrated sample| FC
    EP --> FC
    FC --> Face
    Face --> Display
    Telemetry --> Display
    Info --> Display
```

## Component responsibilities

- **SerialReader** continuously polls the microcontroller over UART (or a mock
  publisher in the simulator) and produces `SensorSample` objects.
- **GyroCalibrator** watches short-term IMU stability windows and learns the
  baseline offsets that should be subtracted before feeding gyro data into the
  face controller.
- **FaceController + EmotionPolicy** translate the calibrated motion cues into a
  target emotion plus facial pose data consumed by the `RoboticFaceWidget`.
- **RoboticFaceWidget** renders eye, brow, and mouth states. It is agnostic of
  where the inputs originate, so both the simulator and the robot runtime reuse
  the same widget.
- **TelemetryPanel** visualizes the raw (non-calibrated) sensor stream, hosts the
  status icon, and reports connection/streaming health.
- **InfoPanel** displays human-friendly metadata (device IP, Wi-Fi SSID) and
  emits the fullscreen toggle signal that both entry points honor.
- **FaceTelemetryDisplay** composes the robotic face with the collapsible overlay
  panels and enforces the top-right docking logic that keeps the controls
  onscreen.

## Execution environments

| Environment | Entry point | Purpose |
|-------------|-------------|---------|
| Simulator   | `simulation_main.py` | Generates pseudo-random `SensorSample` data and exposes a rich control surface for designers to test the face UI without hardware. |
| Robot runtime | `robot_main.py` | Connects to the UART bridge, auto-calibrates gyro offsets, and mirrors the telemetry/info overlays inside a fullscreen kiosk experience. |

Both entry points share the same widget hierarchy and overlays. Only the sensor
source and calibration plumbing differ.
