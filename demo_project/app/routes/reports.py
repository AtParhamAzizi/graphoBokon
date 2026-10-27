"""Report endpoints call through repository factories and background jobs."""

from fastapi import APIRouter

from ..jobs import run_jobs
from ..reports import generate_report
from ..repositories import build_repository

router = APIRouter()


@router.get("/reports/users")
def user_report_route() -> dict:
    return {"report": generate_report(build_repository())}


@router.post("/jobs/run")
def run_jobs_route() -> dict:
    return {"results": run_jobs(build_repository())}
