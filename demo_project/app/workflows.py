"""Cross-feature workflows include nested functions and a recursive call."""

from typing import Callable

from .config import PAGE_SIZE
from .decorators import async_traced, traced
from .events import record_event
from .models import Project, User
from .services import UserService


@traced
def onboard_user(payload: dict, service: UserService) -> User:
    user = service.create(payload)
    project = Project(user.identifier, f"{user.name}'s workspace", user)
    project.validate()
    record_event("project.created", project.describe())
    return user


@async_traced
async def onboard_and_notify(payload: dict, service: UserService) -> User:
    user = onboard_user(payload, service)
    await service.notify(user)
    return user


def build_onboarding_pipeline(service: UserService) -> Callable:
    def create_with_audit(payload: dict) -> User:
        user = onboard_user(payload, service)
        record_event("pipeline.completed", user.describe())
        return user

    return create_with_audit


def batch_users(users: list[User], size: int = PAGE_SIZE) -> list[list[User]]:
    if size <= 0:
        raise ValueError("Batch size must be positive")
    if not users:
        return []
    return [users[:size]] + batch_users(users[size:], size)
