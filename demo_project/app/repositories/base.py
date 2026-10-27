"""Repository contracts provide cross-file inheritance and override targets."""

from abc import ABC, abstractmethod

from ..models import User


class UserRepository(ABC):
    @abstractmethod
    def get(self, identifier: int) -> User:
        raise NotImplementedError

    @abstractmethod
    def save(self, user: User) -> User:
        raise NotImplementedError

    @abstractmethod
    def list_users(self) -> list[User]:
        raise NotImplementedError
