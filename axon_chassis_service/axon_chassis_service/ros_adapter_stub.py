"""ROS adapter placeholders.

This module intentionally contains no ROS imports. It exists so future ROS 2
integration can replace these stubs without changing the core service.
"""

from __future__ import annotations

from .command_arbiter import CommandSource
from .feedback_sinks import FeedbackSink


class RosFeedbackSinkStub(FeedbackSink):
    """This is a placeholder for future ROS 2 integration."""

    async def publish_feedback(self, obj: dict, raw_line: str) -> None:
        pass


class RosCommandSourceStub(CommandSource):
    """This is a placeholder for future ROS 2 integration."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass
