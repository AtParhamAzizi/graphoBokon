"""Validation helpers are shared across models and workflows."""

from .errors import ValidationError


def validate_email(email: str) -> str:
    if "@" not in email or not email.split("@", 1)[0]:
        raise ValidationError("A valid email address is required")
    return email.strip().lower()


def validate_name(name: str) -> str:
    if not name.strip():
        raise ValidationError("A name is required")
    return " ".join(name.split())


def validate_payload(payload: dict) -> dict:
    if not {"id", "name", "email"}.issubset(payload):
        raise ValidationError("The payload needs id, name, and email")
    return {
        "id": int(payload["id"]),
        "name": validate_name(str(payload["name"])),
        "email": validate_email(str(payload["email"])),
    }
