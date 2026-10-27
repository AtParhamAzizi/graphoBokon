"""Domain exception inheritance and explicit raise targets."""


class DomainError(Exception):
    """Base exception for the demo domain."""


class ValidationError(DomainError):
    """A user or project failed validation."""


class UserNotFound(DomainError):
    """A repository or directory could not find a user."""


class DeliveryError(DomainError):
    """An outbound notification was rejected."""
