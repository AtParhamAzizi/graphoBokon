"""Functions are used directly, passed as callbacks, and returned as closures."""

from typing import Callable

from .models import User


def format_user(user: User) -> str:
    return f"{user.name},{user.email}"


def user_sort_key(user: User) -> str:
    return user.name.casefold()


def make_prefixer(prefix: str) -> Callable[[str], str]:
    def add_prefix(value: str) -> str:
        return f"{prefix}: {value}"

    return add_prefix
