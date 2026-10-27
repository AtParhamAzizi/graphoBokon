"""Run an offline workflow without FastAPI, httpx, a server, or network calls."""

from app.jobs import run_jobs, run_report_alias
from app.models import User
from app.plugins import NormalizeNamePlugin, invoke_plugin, normalize_user
from app.reports import generate_report, preview_user
from app.services import build_user_service
from app.workflows import batch_users, build_onboarding_pipeline, onboard_user


def run_demo() -> str:
    service = build_user_service()
    user = onboard_user(
        {"id": 4, "name": "  Katherine Johnson  ", "email": "katherine@example.com"},
        service,
    )
    normalize_user(user)
    invoke_plugin(NormalizeNamePlugin(), user)
    pipeline = build_onboarding_pipeline(service)
    pipeline({"id": 5, "name": "Mary Jackson", "email": "mary@example.com"})
    service.activate(user.identifier)
    batch_users(service.repository.list_users())
    run_jobs(service.repository)
    run_report_alias(service.repository)
    preview_user(User.from_payload({"id": 6, "name": "Annie Easley", "email": "annie@example.com"}))
    return generate_report(service.repository)


if __name__ == "__main__":
    print(run_demo())
