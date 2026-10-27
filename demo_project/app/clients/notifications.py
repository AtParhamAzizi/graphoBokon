"""A second HTTP dependency is intentionally separate from local calls."""

from ..config import NOTIFICATION_URL
from ..errors import DeliveryError
from ..events import record_event
from ..models import User


class NotificationClient:
    async def send_welcome(self, user: User) -> None:
        import httpx as transport

        async with transport.AsyncClient() as session:
            response = await session.post(
                NOTIFICATION_URL,
                json={"email": user.email, "message": f"Welcome, {user.name}!"},
            )
            if response.status_code >= 400:
                raise DeliveryError("The notification service rejected the message")
            record_event("notification.sent", user.email)
