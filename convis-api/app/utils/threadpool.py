from typing import Any, Callable, TypeVar
from fastapi.concurrency import run_in_threadpool

T = TypeVar("T")


async def run_in_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Run a blocking function in a threadpool to avoid blocking the event loop.
    Accepts a callable plus args/kwargs and returns the function result.
    """
    return await run_in_threadpool(lambda: func(*args, **kwargs))
