# Axon Runtime Workflow (Non-UI)

This walkthrough focuses on how the Axon codebase ingests telemetry, applies
robot-control logic, and shares the processed state with any UI surface. UI
widgets such as `RoboticFaceWidget` or the overlays are consumers of this
pipeline and therefore mentioned only when necessary to explain data hand-offs.

## 1. Bootstrapping the runtime

1. **Entry point selection**
   - `robot_main.py` is executed on hardware.
   - `simulation_main.py` runs on development laptops and injects mock sensor data.
2. **Logging + OSI setup**
   - Both entry points create an `axon_ros.osi.OsiStack` so each component can be
     registered against a networking layer (physical, transport, session, etc.).
3. **Hardware readiness** (robot only)
   - `robot_main.py` sleeps for five seconds to let the MCU/serial bus stabilize
     before touching `/dev/ttyAMA0`.
4. **Serial transport**
   - `robot_control.serial_reader.SerialReadWriter` is constructed with the
     configured port and baud rate. It spawns a background thread that emits
     parsed `SensorSample` objects and keeps the latest sample in memory.

## 2. Sensor acquisition + normalization

1. **SensorSample parsing**
   - `SerialReadWriter._run` drains newline-delimited JSON payloads, decodes
     them into `robot_control.sensor_data.SensorSample`, and filters out
     simulator-only frames.
2. **Calibration**
   - `robot_control.gyro_calibrator.GyroCalibrator` receives each sample through
     `RobotRuntime._apply_calibration`. When the robot has been stationary for a
     configurable window, it learns baseline offsets for yaw/pitch/roll and
     subtracts them from future samples.
3. **Emotion policy**
   - `robot_control.emotion_policy.EmotionPolicy` converts the normalized motion
     and sensor metadata into an emotion request. It exposes convenience methods
     used by both the robot runtime and simulator (e.g., presets, idle logic).
4. **Face controller**
   - `robot_control.face_controller.FaceController` blends the calibrated sample
     with the requested emotion to generate a low-level pose payload. Although
     the widget consumes this data, the controller itself remains UI-agnostic.

## 3. Runtime loop (`axon_ros.runtime.RobotRuntime`)

1. **Qt timer**
   - Upon `start()`, a `QTimer` ticks every `poll_interval_ms` (40 ms by default).
2. **Serial polling**
   - Each tick calls `SerialReadWriter.pop_latest()`. If a sample is available,
     the runtime applies calibration, emotion policy, and controller updates.
3. **Telemetry fan-out**
   - The freshly calibrated sample is pushed to the telemetry overlay (UI), the
     `SerialBridgeServer`, and any other registered consumers.
4. **Bridge integration**
   - The runtime wires the serial reader's `add_line_consumer` hook to the
     telemetry panel and the TCP bridge so both receive raw serial text for
     logging or debugging.
5. **Lifecycle management**
   - `RobotRuntime.stop()` halts the timer, stops the serial reader, and shuts
     down the TCP bridge. `robot_main.py` hooks this into Qt's `aboutToQuit`.

## 4. TCP bridge and remote access

1. **Bridge startup**
   - `robot_control.serial_bridge_server.SerialBridgeServer` registers itself as a
     line consumer so every decoded UART frame is forwarded to TCP clients.
2. **Telemetry framing**
   - Structured telemetry is emitted as `telemetry {json}` lines, making it easy
     for remote tools to detect machine-readable payloads while still receiving
     the raw serial log.
3. **Command passthrough**
   - Remote operators send newline-delimited commands; the bridge relays them via
     `SerialReadWriter.send_command`. Echo/error responses are sent back over the
     same socket.
4. **Clients**
   - `axon_ui.bridge_client.SerialBridgeClient` (used by `misc/remote_ui_main.py`)
     and `misc/serial_command_client.py` connect to the bridge and subscribe to
     both telemetry and log lines.

## 5. Simulator workflow

1. **Policy + calibrator reuse**
   - `simulation_main.py` instantiates the same `EmotionPolicy` and
     `GyroCalibrator` objects so their behavior mirrors hardware.
2. **Synthetic samples**
   - `axon_ros.ui.SimulatorMainWindow` synthesizes `SensorSample` payloads when
     the user tweaks sliders or presets. Those samples are pushed directly
     through the calibration/policy/controller pipeline without a serial reader.
3. **Bridge awareness**
   - Optional `--bridge-host/--bridge-port` arguments pre-fill the Robot Link tab
     so teams can quickly pair the simulator UI with a live robot bridge.
4. **Shutdown path**
   - `SimulatorMainWindow.shutdown()` stops any background generators and closes
     down Qt resources, mirroring the robot runtime's lifecycle expectations.

## 6. Extending the workflow

- **New sensor inputs** can reuse `SerialReadWriter`'s interface by producing
  newline-delimited JSON frames that match `SensorSample.from_json`.
- **Alternative calibration/policy modules** can be injected into
  `RobotRuntime` because it accepts the calibrator and controller objects during
  construction.
- **Additional telemetry sinks** can subscribe via `SerialReadWriter.add_line_consumer`
  or by listening to the TCP bridge's structured frames.

This workflow captures every moving piece involved in processing telemetry and
controlling the robot face, ensuring contributors understand how the runtime
operates independently from the UI implementation details.
