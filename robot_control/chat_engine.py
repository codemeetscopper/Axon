"""Claude AI chatbot engine with tool use, vision, and persistent memory for Axon."""

from __future__ import annotations

import base64
import json
import logging
import os
import pathlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import anthropic

LOGGER = logging.getLogger(__name__)

VALID_EMOTIONS = (
    "neutral", "happy", "sad", "surprised", "sleepy", "curious",
    "excited", "angry", "fearful", "disgusted", "smirk", "proud",
)

MEMORY_PATH = pathlib.Path.home() / "Desktop" / "Axon" / "axon_memory.json"

DEFAULT_SYSTEM_PROMPT = """\
You are Axon, a friendly and expressive robot built on a Raspberry Pi 5.
You have a face that shows emotions, wheels to move, a pan/tilt camera gimbal, \
an OLED display, and two microphones. You can search the web and see through your camera.

RESPONSE RULES:
- Always speak naturally in 1-3 short sentences. Your text is spoken aloud via TTS.
- Use the set_emotion tool to show emotions instead of JSON tags.
- After using tools, always say something about what happened.
- You can chain multiple tools in one turn (e.g. look around then move).
- Use save_memory to remember important facts about people, preferences, names.
- Use recall_memory to check what you know before asking again.

CAPABILITIES:
- Move wheels, navigate using camera vision, pan/tilt camera to look around
- Capture camera frames and describe what you see
- Search the web for any information
- Remember people's names and facts across conversations
- Sing songs by speaking lyrics with emotion
- Display text on OLED screen\
"""

TOOLS = [
    {
        "name": "move_robot",
        "description": "Drive the robot's wheels. Positive = forward, negative = backward. Values: -0.5 to 0.5. Always set a duration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "left_speed": {"type": "number", "description": "-0.5 to 0.5"},
                "right_speed": {"type": "number", "description": "-0.5 to 0.5"},
                "duration_s": {"type": "number", "description": "Seconds to move (0.5-5.0)"},
            },
            "required": ["left_speed", "right_speed"],
        },
    },
    {
        "name": "stop_robot",
        "description": "Stop all wheel movement immediately.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "pan_tilt_camera",
        "description": "Move camera gimbal. Pan: 0=left, 128=center, 255=right. Tilt: 0=down, 128=center, 255=up.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pan": {"type": "integer", "description": "0-255, 128=center"},
                "tilt": {"type": "integer", "description": "0-255, 128=center"},
            },
            "required": ["pan", "tilt"],
        },
    },
    {
        "name": "look_around",
        "description": "Scan the environment by panning the camera left, center, right and capturing images at each position. Returns descriptions of what's visible. Use when asked to look around or explore visually.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "navigate_visual",
        "description": "Autonomous visual navigation. Captures camera frames, moves, and repeats until goal is reached or max steps hit. You do NOT need to call this multiple times — it runs a full navigation loop internally and returns the result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "Navigation goal (e.g. 'go to the door', 'explore the room')"},
                "max_steps": {"type": "integer", "description": "Max navigation steps (default 5, max 10)"},
            },
            "required": ["goal"],
        },
    },
    {
        "name": "capture_camera",
        "description": "Take a single photo and see what's in front of the camera.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "display_oled",
        "description": "Show text on the OLED display (4 lines, 0-3).",
        "input_schema": {
            "type": "object",
            "properties": {
                "line": {"type": "integer", "description": "Line 0-3"},
                "text": {"type": "string", "description": "Text to show"},
            },
            "required": ["line", "text"],
        },
    },
    {
        "name": "read_sensors",
        "description": "Read IMU orientation, wheel speeds, temperature, battery voltage.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_emotion",
        "description": "Change facial expression. Use this to express emotions instead of JSON tags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "emotion": {"type": "string", "description": "neutral/happy/sad/surprised/sleepy/curious/excited/angry/fearful/disgusted/smirk/proud"},
            },
            "required": ["emotion"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web. Use for weather, news, facts, or anything you don't know.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_current_time",
        "description": "Get current date and time.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "save_memory",
        "description": "Save a fact to persistent memory. Use for people's names, preferences, important information that should be remembered across conversations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Short key (e.g. 'owner_name', 'favorite_color')"},
                "value": {"type": "string", "description": "The fact to remember"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "recall_memory",
        "description": "Recall all saved memories. Use this at the start of conversations or when you need context about the user.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


@dataclass(slots=True)
class ChatResponse:
    text: str
    emotion: str


class ChatEngine:
    """Stateful conversation with Claude, supporting tools, vision, and persistent memory."""

    def __init__(
        self,
        serial_reader: Any = None,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        max_history: int = 30,
        system_prompt: Optional[str] = None,
    ) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set.")
        self._client = anthropic.Anthropic(api_key=key)
        self._model = model
        self._max_history = max_history
        self._system = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._history: list[dict] = []
        self._serial = serial_reader
        self._last_camera_b64: str | None = None
        self._memory = self._load_memory()
        # Inject memory context into system prompt
        if self._memory:
            mem_str = "\n".join(f"- {k}: {v}" for k, v in self._memory.items())
            self._system += f"\n\nYOUR SAVED MEMORIES:\n{mem_str}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def send(self, user_text: str) -> ChatResponse:
        self._history.append({"role": "user", "content": user_text})
        self._trim_history()
        try:
            return self._converse()
        except Exception:
            LOGGER.exception("Claude API call failed")
            self._history.pop()
            return ChatResponse(text="I'm having trouble thinking right now.", emotion="sad")

    def clear_history(self) -> None:
        self._history.clear()

    # ------------------------------------------------------------------
    # Tool-use conversation loop
    # ------------------------------------------------------------------
    def _converse(self) -> ChatResponse:
        max_rounds = 8
        for _ in range(max_rounds):
            message = self._client.messages.create(
                model=self._model,
                max_tokens=600,
                system=self._system,
                messages=self._history,
                tools=TOOLS,
            )

            if message.stop_reason == "tool_use":
                self._history.append({"role": "assistant", "content": message.content})
                tool_results = []
                for block in message.content:
                    if block.type == "tool_use":
                        result = self._execute_tool(block.name, block.input)
                        LOGGER.info("Tool %s(%s) -> %s", block.name, block.input, str(result)[:200])
                        if block.name == "capture_camera" and self._last_camera_b64:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": [
                                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": self._last_camera_b64}},
                                    {"type": "text", "text": "Describe what you see briefly."},
                                ],
                            })
                            self._last_camera_b64 = None
                        elif block.name in ("look_around", "navigate_visual") and self._last_camera_b64:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": [
                                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": self._last_camera_b64}},
                                    {"type": "text", "text": result},
                                ],
                            })
                            self._last_camera_b64 = None
                        else:
                            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
                self._history.append({"role": "user", "content": tool_results})
                continue

            # Final text response — extract spoken text
            text_parts = []
            for block in message.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            raw = "\n".join(text_parts).strip()
            self._history.append({"role": "assistant", "content": raw})
            self._trim_history()

            # Clean up any accidental JSON emotion tags
            text, emotion = self._parse_response(raw)
            LOGGER.info("Claude: %s [%s]", text, emotion)
            return ChatResponse(text=text, emotion=emotion)

        return ChatResponse(text="Let me think about that differently.", emotion="curious")

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------
    def _execute_tool(self, name: str, params: dict) -> str:
        try:
            handler = {
                "move_robot": self._tool_move,
                "stop_robot": lambda p: self._tool_stop(),
                "pan_tilt_camera": self._tool_pan_tilt,
                "look_around": lambda p: self._tool_look_around(),
                "navigate_visual": self._tool_navigate_visual,
                "capture_camera": lambda p: self._tool_capture_camera(),
                "display_oled": self._tool_oled,
                "read_sensors": lambda p: self._tool_read_sensors(),
                "set_emotion": self._tool_set_emotion,
                "web_search": self._tool_web_search,
                "get_current_time": lambda p: self._tool_get_time(),
                "save_memory": self._tool_save_memory,
                "recall_memory": lambda p: self._tool_recall_memory(),
            }.get(name)
            if handler:
                return handler(params)
            return f"Unknown tool: {name}"
        except Exception as exc:
            LOGGER.exception("Tool %s failed", name)
            return f"Error: {exc}"

    def _tool_move(self, params: dict) -> str:
        if not self._serial:
            return "Error: no serial connection"
        left = max(-0.5, min(0.5, float(params.get("left_speed", 0))))
        right = max(-0.5, min(0.5, float(params.get("right_speed", 0))))
        duration = max(0.1, min(5.0, float(params.get("duration_s", 1.0))))
        self._serial.send_command(json.dumps({"T": 1, "L": left, "R": right}))
        import threading, time as _time
        def stop_later():
            _time.sleep(duration)
            try:
                self._serial.send_command(json.dumps({"T": 1, "L": 0, "R": 0}))
            except Exception:
                pass
        threading.Thread(target=stop_later, daemon=True).start()
        return f"Moving L={left}, R={right} for {duration}s"

    def _tool_stop(self) -> str:
        if not self._serial:
            return "Error: no serial connection"
        self._serial.send_command(json.dumps({"T": 1, "L": 0, "R": 0}))
        return "Stopped"

    def _tool_pan_tilt(self, params: dict) -> str:
        if not self._serial:
            return "Error: no serial connection"
        pan = max(0, min(255, int(params.get("pan", 128))))
        tilt = max(0, min(255, int(params.get("tilt", 128))))
        self._serial.send_command(json.dumps({"T": 132, "IO4": pan, "IO5": tilt}))
        return f"Camera moved to pan={pan}, tilt={tilt}"

    def _tool_look_around(self) -> str:
        """Pan camera left, center, right and capture at center for vision analysis."""
        if not self._serial:
            return "Error: no serial connection"
        import time as _time
        observations = []
        for label, pan in [("left", 50), ("center", 128), ("right", 200)]:
            self._serial.send_command(json.dumps({"T": 132, "IO4": pan, "IO5": 128}))
            _time.sleep(0.8)
            self._tool_capture_camera()
            if self._last_camera_b64:
                try:
                    msg = self._client.messages.create(
                        model=self._model, max_tokens=80,
                        messages=[{"role": "user", "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": self._last_camera_b64}},
                            {"type": "text", "text": f"Briefly describe what you see (looking {label})."},
                        ]}],
                    )
                    observations.append(f"{label}: {msg.content[0].text.strip()}")
                except Exception:
                    observations.append(f"{label}: [capture failed]")
                self._last_camera_b64 = None
        # Return to center
        self._serial.send_command(json.dumps({"T": 132, "IO4": 128, "IO5": 128}))
        _time.sleep(0.5)
        self._tool_capture_camera()  # final center frame for vision
        return "Scanned surroundings:\n" + "\n".join(observations)

    def _tool_navigate_visual(self, params: dict) -> str:
        """Autonomous navigation loop: capture → decide → move → verify."""
        import time as _time
        goal = params.get("goal", "explore safely")
        max_steps = min(10, max(1, int(params.get("max_steps", 5))))

        if not self._serial:
            return "Error: no serial connection"

        log = []
        for step in range(1, max_steps + 1):
            # 1. Capture current view
            cap_result = self._tool_capture_camera()
            if "Error" in cap_result or not self._last_camera_b64:
                log.append(f"Step {step}: camera failed")
                break

            # 2. Ask Claude (separate mini-call) what to do
            nav_prompt = (
                f"You are navigating a robot toward this goal: '{goal}'. "
                f"This is step {step}/{max_steps}. "
                "Look at this camera image. Respond with ONLY a JSON object: "
                '{"action": "forward|left|right|stop", "reason": "brief reason"}. '
                'Use "stop" if the goal is reached or path is blocked.'
            )
            try:
                nav_msg = self._client.messages.create(
                    model=self._model,
                    max_tokens=100,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": self._last_camera_b64}},
                            {"type": "text", "text": nav_prompt},
                        ],
                    }],
                )
                nav_text = nav_msg.content[0].text.strip()
                self._last_camera_b64 = None
            except Exception as exc:
                log.append(f"Step {step}: vision API error: {exc}")
                break

            # 3. Parse action
            try:
                # Extract JSON from response
                start = nav_text.index("{")
                end = nav_text.rindex("}") + 1
                nav_data = json.loads(nav_text[start:end])
                action = nav_data.get("action", "stop")
                reason = nav_data.get("reason", "")
            except (ValueError, json.JSONDecodeError):
                action = "stop"
                reason = f"Could not parse: {nav_text[:80]}"

            log.append(f"Step {step}: {action} — {reason}")
            LOGGER.info("Navigate step %d: %s — %s", step, action, reason)

            if action == "stop":
                break

            # 4. Execute movement
            if action == "forward":
                self._serial.send_command(json.dumps({"T": 1, "L": 0.2, "R": 0.2}))
                _time.sleep(1.2)
            elif action == "left":
                self._serial.send_command(json.dumps({"T": 1, "L": -0.15, "R": 0.15}))
                _time.sleep(0.8)
            elif action == "right":
                self._serial.send_command(json.dumps({"T": 1, "L": 0.15, "R": -0.15}))
                _time.sleep(0.8)

            self._serial.send_command(json.dumps({"T": 1, "L": 0, "R": 0}))
            _time.sleep(0.3)

        # 5. Final verification photo
        self._tool_capture_camera()
        summary = "\n".join(log)
        return f"Navigation complete ({len(log)} steps):\n{summary}\nFinal camera frame attached for verification."

    def _tool_oled(self, params: dict) -> str:
        if not self._serial:
            return "Error: no serial connection"
        line = max(0, min(3, int(params.get("line", 0))))
        text = str(params.get("text", ""))[:20]
        self._serial.send_command(json.dumps({"T": 3, "lineNum": line, "Text": text}))
        return f"Displayed '{text}' on line {line}"

    def _tool_read_sensors(self) -> str:
        if not self._serial:
            return "Error: no serial connection"
        sample = self._serial.pop_latest()
        if sample is None:
            return "No sensor data available"
        return json.dumps({
            "left_speed": sample.left_speed, "right_speed": sample.right_speed,
            "roll": round(sample.roll, 1), "pitch": round(sample.pitch, 1),
            "yaw": round(sample.yaw, 1),
            "temperature_c": round(sample.temperature_c, 1),
            "voltage_v": round(sample.voltage_v, 2),
        })

    def _tool_set_emotion(self, params: dict) -> str:
        emotion = params.get("emotion", "neutral")
        if emotion in VALID_EMOTIONS:
            return f"Emotion set to {emotion}"
        return f"Unknown emotion. Use: {', '.join(VALID_EMOTIONS)}"

    def _tool_web_search(self, params: dict) -> str:
        query = params.get("query", "")
        if not query:
            return "No query"
        try:
            from ddgs import DDGS
            results = DDGS().text(query, max_results=3)
            if not results:
                return "No results for: " + query
            return "\n".join(f"{r.get('title','')} - {r.get('body','')}" for r in results)
        except Exception as exc:
            return f"Search failed: {exc}"

    def _tool_get_time(self) -> str:
        return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    def _tool_capture_camera(self) -> str:
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return "Error: camera capture failed"
            _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
            self._last_camera_b64 = base64.standard_b64encode(jpg.tobytes()).decode()
            return "CAMERA_IMAGE_CAPTURED"
        except Exception as exc:
            return f"Camera error: {exc}"

    # ------------------------------------------------------------------
    # Persistent memory
    # ------------------------------------------------------------------
    def _tool_save_memory(self, params: dict) -> str:
        key = params.get("key", "").strip()
        value = params.get("value", "").strip()
        if not key or not value:
            return "Need both key and value"
        self._memory[key] = value
        self._save_memory()
        return f"Remembered: {key} = {value}"

    def _tool_recall_memory(self) -> str:
        if not self._memory:
            return "No memories saved yet."
        lines = [f"- {k}: {v}" for k, v in self._memory.items()]
        return "Your memories:\n" + "\n".join(lines)

    def _load_memory(self) -> dict:
        try:
            if MEMORY_PATH.exists():
                data = json.loads(MEMORY_PATH.read_text())
                LOGGER.info("Loaded %d memories from %s", len(data), MEMORY_PATH)
                return data
        except Exception:
            LOGGER.exception("Failed to load memory")
        return {}

    def _save_memory(self) -> None:
        try:
            MEMORY_PATH.write_text(json.dumps(self._memory, indent=2))
            LOGGER.info("Saved %d memories to %s", len(self._memory), MEMORY_PATH)
        except Exception:
            LOGGER.exception("Failed to save memory")

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------
    def _parse_response(self, raw: str) -> tuple[str, str]:
        text = raw.strip()
        emotion = "neutral"

        # Strip any JSON emotion tags Claude might still add
        lines = text.split("\n")
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("{") and "emotion" in stripped:
                try:
                    data = json.loads(stripped)
                    e = data.get("emotion", "")
                    if e in VALID_EMOTIONS:
                        emotion = e
                    continue  # skip this line
                except json.JSONDecodeError:
                    pass
            clean_lines.append(line)

        text = "\n".join(clean_lines).strip()

        # If nothing left, use raw
        if not text or text.startswith("{"):
            text = raw.strip()
            # Still nothing usable — last resort
            if not text or text.startswith("{"):
                text = "Done!"

        return text, emotion

    def _trim_history(self) -> None:
        while len(self._history) > self._max_history:
            self._history.pop(0)
