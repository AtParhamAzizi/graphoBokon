"""Optional HTTP integration; importing this module makes no requests."""

from ..config import DIRECTORY_URL
from ..errors import UserNotFound
from ..models import User


class DirectoryClient:
    async def fetch(self, identifier: int) -> User:
        from httpx import AsyncClient as Client

        async with Client() as session:
            response = await session.get(f"{DIRECTORY_URL}/{identifier}")
            if response.status_code == 404:
                raise UserNotFound(f"The directory has no user {identifier}")
            response.raise_for_status()
            return User.from_payload(response.json())

    async def search(self, query: str) -> list[User]:
        import httpx as transport

        async with transport.AsyncClient() as session:
            response = await session.get(DIRECTORY_URL, params={"query": query})
            response.raise_for_status()
            return [User.from_payload(payload) for payload in response.json()]
