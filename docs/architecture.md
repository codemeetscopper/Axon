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
        Telemetry[TelemetryPanel\n(axon_ui.telemetry)]
        Info[InfoPanel\n(axon_ui.telemetry)]
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
- **SerialCommandServer** mirrors the UART link over TCP so remote tools can
  issue manual commands and watch the live telemetry stream. The included
  PySide6 `serial_command_client.py` application provides a dashboard UI for
  driving that bridge from another computer.
- **RemoteBridgeController** (in `robot_control.remote_bridge`) embeds the same
  TCP client inside the simulator so a "Robot link" card can hand control of the
  face/telemetry overlays to live hardware whenever a connection to
  `192.168.1.169:8765` is established.
- **SerialBridgeConnection** (in `axon_ui.bridge_client`) is the reusable Qt
  socket helper that powers both the simulator's remote card and the standalone
  bridge client.
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
| Simulator   | `simulation_main.py` | Generates pseudo-random `SensorSample` data, exposes a rich control surface for designers, and now includes a "Robot link" card that can stream telemetry from the hardware bridge at `192.168.1.169`. |
| Robot runtime | `robot_main.py` | Connects to the UART bridge, auto-calibrates gyro offsets, and mirrors the telemetry/info overlays inside a fullscreen kiosk experience. |

Both entry points share the same widget hierarchy and overlays. Only the sensor
source and calibration plumbing differ.
