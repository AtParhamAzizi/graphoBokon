"""Write routes connect HTTP entry points to services and workflows."""

from fastapi import APIRouter

from ..models import User
from ..services import activate_user, build_user_service, create_user, fetch_user
from ..workflows import onboard_and_notify

router = APIRouter()


@router.post("/users")
def create_user_route(payload: dict) -> User:
    return create_user(payload)


@router.post("/users/{user_id}/activate")
def activate_user_route(user_id: int) -> User:
    return activate_user(user_id)


@router.post("/users/onboard")
async def onboard_user_route(payload: dict) -> User:
    return await onboard_and_notify(payload, build_user_service())


@router.get("/users/{user_id}/preview")
async def preview_user_route(user_id: int) -> dict:
    from ..reports import preview_user

    user = await fetch_user(user_id)
    return {"preview": preview_user(user)}
