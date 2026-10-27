"""Jobs use dotted module imports, aliases, async calls, and runtime dispatch."""

import app.reports

from .events import record_event
from .models import User
from .repositories import UserRepository
from .services import UserService


class Job:
    def run(self, repository: UserRepository) -> str:
        raise NotImplementedError


class ReportJob(Job):
    def run(self, repository: UserRepository) -> str:
        return app.reports.generate_report(repository)


class AuditJob(Job):
    def run(self, repository: UserRepository) -> str:
        users = repository.list_users()
        record_event("audit", f"{len(users)} users")
        return f"Audited {len(users)} users"


def run_jobs(repository: UserRepository) -> list[str]:
    jobs = [ReportJob(), AuditJob()]
    return [job.run(repository) for job in jobs]


def run_report_alias(repository: UserRepository) -> str:
    render = app.reports.generate_report
    return render(repository)


async def refresh_users(service: UserService, identifiers: list[int]) -> list[User]:
    return [await service.fetch(identifier) for identifier in identifiers]
