# Axon Face Runtime — Architecture Briefing

## Slide 1 — Mission
- Deliver a shared UI stack for both the desktop simulator and the physical robot.
- Keep the expressive `RoboticFaceWidget` front-and-center while surfacing telemetry.
- Provide operators with immediate status (connection, IP, Wi-Fi, fullscreen).

## Slide 2 — Key Modules
- `simulation_main.FaceTelemetryDisplay`: composite widget that layers the face and overlay dock.
- `axon_ui.telemetry.TelemetryPanel`: raw sensor viewer + status icon.
- `axon_ui.telemetry.InfoPanel`: metadata card with fullscreen toggle signal.
- `robot_control.SerialReader`: pulls `SensorSample` objects from UART.
- `robot_control.serial_command_server.SerialCommandServer`: re-shares the UART
  link over TCP so remote tools can issue manual commands and stream telemetry.
- `robot_control.remote_bridge.RemoteBridgeController`: reuses the TCP bridge
  client inside the simulator so operators can hand control to the live robot
  from the new "Robot link" card (default IP `192.168.1.169`).
- `axon_ui.bridge_client.SerialBridgeConnection`: lightweight Qt socket helper
  consumed by both the simulator and the standalone client.
- `robot_control.GyroCalibrator`: learns gyro offsets after 3 s of stability.
- `robot_control.FaceController` + `EmotionPolicy`: converts normalized motion into mouth/eye poses.

## Slide 3 — Data Flow
1. **Sensors / simulator** emit `SensorSample` packets.
2. **SerialReader** pushes samples to the gyro calibrator and telemetry panel simultaneously.
3. **GyroCalibrator** updates offsets and passes normalized readings to `FaceController`.
4. **FaceController** asks the `EmotionPolicy` for the matching expression and updates the face widget.
5. **FaceTelemetryDisplay** overlays telemetry/info panels, ensuring only one is expanded.

## Slide 4 — UI Behavior
- Overlay dock is pinned to the top-right and expands only to the left.
- Telemetry and info bars now receive explicit width budgets so each component
  fills the overlay dock without jitter.
- A dedicated "Robot link" card sits atop the simulator panel so the embedded
  face can stream telemetry straight from the robot via TCP.
- Info panel arranges IP + Wi-Fi labels horizontally and hosts the fullscreen toggle.
- Both panels start collapsed so the face consumes the full canvas at boot.

## Slide 5 — Extensibility Notes
- Additional overlays can be injected into `FaceTelemetryDisplay` without layout changes.
- Alternative sensor sources (e.g., file replay) can plug into `SerialReader`'s interface.
- The calibrator exposes `GyroCalibrator.reset()` for re-baselining during runtime.
- Presentation-friendly info can be added to `InfoPanel` via new label rows or actions.
