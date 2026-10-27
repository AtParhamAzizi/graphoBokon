"""Callbacks and typed event subscribers connect otherwise separate features."""

from dataclasses import dataclass
from typing import Callable

from .models import User


@dataclass
class AuditEvent:
    topic: str
    detail: str


EVENT_LOG: list[AuditEvent] = []


def record_event(topic: str, detail: str) -> AuditEvent:
    event = AuditEvent(topic, detail)
    EVENT_LOG.append(event)
    return event


def on_user_created(user: User) -> None:
    record_event("user.created", user.describe())


def on_user_activated(user: User) -> None:
    record_event("user.activated", user.describe())


class EventBus:
    def __init__(self):
        self.subscribers = {}

    def subscribe(self, topic: str, callback: Callable[[User], None]) -> None:
        self.subscribers.setdefault(topic, []).append(callback)

    def publish(self, topic: str, user: User) -> None:
        for callback in self.subscribers.get(topic, []):
            callback(user)


def build_event_bus() -> EventBus:
    bus = EventBus()
    bus.subscribe("user.created", on_user_created)
    bus.subscribe("user.activated", on_user_activated)
    return bus
