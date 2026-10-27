"""Application services join persistence, validation, events, and HTTP clients."""

from .clients import NotificationClient, UserDirectory
from .decorators import async_traced, traced
from .errors import UserNotFound
from .events import EventBus, build_event_bus
from .models import User
from .repositories import UserRepository, build_repository
from .validators import validate_payload


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        directory: UserDirectory,
        notifier: NotificationClient,
        events: EventBus,
    ):
        self.repository = repository
        self.directory = directory
        self.notifier = notifier
        self.events = events

    @traced
    def create(self, payload: dict) -> User:
        user = User.from_payload(validate_payload(payload))
        self.repository.save(user)
        self.events.publish("user.created", user)
        return user

    @async_traced
    async def fetch(self, identifier: int) -> User:
        try:
            return self.repository.get(identifier)
        except UserNotFound:
            user = await self.directory.fetch(identifier)
            return self.repository.save(user)

    @traced
    def activate(self, identifier: int) -> User:
        user = self.repository.get(identifier)
        user.activate()
        self.events.publish("user.activated", user)
        return self.repository.save(user)

    async def notify(self, user: User) -> None:
        await self.notifier.send_welcome(user)


def build_user_service() -> UserService:
    return UserService(
        build_repository(), UserDirectory(), NotificationClient(), build_event_bus()
    )


DEFAULT_SERVICE = build_user_service()


async def fetch_user(user_id: int) -> User:
    return await DEFAULT_SERVICE.fetch(user_id)


def create_user(payload: dict) -> User:
    return DEFAULT_SERVICE.create(payload)


def activate_user(user_id: int) -> User:
    return DEFAULT_SERVICE.activate(user_id)
