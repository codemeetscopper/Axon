from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable


logger = logging.getLogger(__name__)


async def shielded(task: Awaitable[None], name: str) -> None:
    try:
        await task
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Task %s crashed", name)


def create_task(coro: Awaitable[None], name: str) -> asyncio.Task:
    return asyncio.create_task(shielded(coro, name), name=name)


async def wait_for_cancel(*tasks: asyncio.Task) -> None:
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        raise


async def cancel_and_wait(*tasks: asyncio.Task) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
