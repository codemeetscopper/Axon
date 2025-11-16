# Axon Face Runtime — Architecture Briefing

## Slide 1 — Mission
- Deliver a shared UI stack for both the desktop simulator and the physical robot.
- Keep the expressive `RoboticFaceWidget` front-and-center while surfacing telemetry.
- Provide operators with immediate status (connection, IP, Wi-Fi, fullscreen).

## Slide 2 — Key Modules
- `axon_ros.ui.face_telemetry_display.FaceTelemetryDisplay`: composite widget that layers the face and overlay dock.
- `axon_ui.telemetry_panel.TelemetryPanel`: raw sensor viewer + status icon.
- `axon_ui.info_panel.InfoPanel`: metadata card with fullscreen toggle signal.
- `robot_control.SerialReader`: pulls `SensorSample` objects from UART.
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
- Telemetry bar uses a fixed width budget after the minimized info icon.
- Info panel arranges IP + Wi-Fi labels horizontally and hosts the fullscreen toggle.
- Both panels start collapsed so the face consumes the full canvas at boot.

## Slide 5 — Extensibility Notes
- Additional overlays can be injected into `FaceTelemetryDisplay` without layout changes.
- Alternative sensor sources (e.g., file replay) can plug into `SerialReader`'s interface.
- The calibrator exposes `GyroCalibrator.reset()` for re-baselining during runtime.
- Presentation-friendly info can be added to `InfoPanel` via new label rows or actions.
