"""Application entry point; scanning this file never starts a server."""

from fastapi import FastAPI, HTTPException

from .config import APPLICATION_NAME
from .errors import UserNotFound
from .models import User
from .routes import health_router, reports_router, users_router
from .services import fetch_user

app = FastAPI(title=APPLICATION_NAME)
app.include_router(health_router)
app.include_router(reports_router)
app.include_router(users_router)


@app.get("/users/{user_id}")
async def user_route(user_id: int) -> User:
    try:
        return await fetch_user(user_id)
    except UserNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
