"""Domain models show inheritance, overrides, classmethods, and type usage."""

from dataclasses import dataclass

from .errors import ValidationError
from .validators import validate_email, validate_name


@dataclass
class Entity:
    identifier: int

    def validate(self) -> None:
        if self.identifier <= 0:
            raise ValidationError("Identifiers must be positive")

    def describe(self) -> str:
        return f"Entity #{self.identifier}"


@dataclass
class User(Entity):
    name: str
    email: str
    active: bool = True

    @classmethod
    def from_payload(cls, payload: dict) -> "User":
        return cls(
            int(payload["id"]),
            str(payload["name"]),
            str(payload["email"]),
            bool(payload.get("active", True)),
        )

    def validate(self) -> None:
        super().validate()
        self.name = validate_name(self.name)
        self.email = validate_email(self.email)

    def describe(self) -> str:
        return f"{super().describe()}: {self.name} <{self.email}>"

    def activate(self) -> "User":
        self.active = True
        self.validate()
        return self


@dataclass
class Project(Entity):
    name: str
    owner: User

    def validate(self) -> None:
        super().validate()
        self.name = validate_name(self.name)
        self.owner.validate()

    def describe(self) -> str:
        return f"{self.name}, owned by {self.owner.name}"
