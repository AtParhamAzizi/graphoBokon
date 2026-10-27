"""Concrete repositories show overrides, super calls, and instance methods."""

from ..config import DEMO_USERS
from ..errors import UserNotFound
from ..models import User
from .base import UserRepository


class MemoryUserRepository(UserRepository):
    def __init__(self):
        self.users = {}

    def get(self, identifier: int) -> User:
        user = self.users.get(identifier)
        if user is None:
            raise UserNotFound(f"User {identifier} was not found")
        return user

    def save(self, user: User) -> User:
        user.validate()
        self.users[user.identifier] = user
        return user

    def list_users(self) -> list[User]:
        return list(self.users.values())


class ActiveUserRepository(MemoryUserRepository):
    def get(self, identifier: int) -> User:
        user = super().get(identifier)
        if not user.active:
            raise UserNotFound(f"User {identifier} is inactive")
        return user

    def list_users(self) -> list[User]:
        return [user for user in super().list_users() if user.active]


def build_repository() -> MemoryUserRepository:
    repository = MemoryUserRepository()
    for payload in DEMO_USERS:
        repository.save(User.from_payload(payload))
    return repository
