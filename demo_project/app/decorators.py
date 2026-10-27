"""Local decorators include nested wrappers and returned function references."""

from functools import wraps
from typing import Callable

from .events import record_event


def traced(function: Callable) -> Callable:
    @wraps(function)
    def wrapped(*arguments, **keywords):
        record_event("trace", function.__name__)
        return function(*arguments, **keywords)

    return wrapped


def async_traced(function: Callable) -> Callable:
    @wraps(function)
    async def wrapped(*arguments, **keywords):
        record_event("async.trace", function.__name__)
        return await function(*arguments, **keywords)

    return wrapped
