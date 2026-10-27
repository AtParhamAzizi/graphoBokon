"""Reports exercise module aliases, factories, callbacks, and method overrides."""

from typing import Callable

from . import formatters as presentation
from .decorators import traced
from .models import User
from .repositories import UserRepository


class ReportBuilder:
    def render(
        self, users: list[User], formatter: Callable[[User], str]
    ) -> str:
        return "\n".join(map(formatter, users))


class CsvReportBuilder(ReportBuilder):
    def render(
        self, users: list[User], formatter: Callable[[User], str]
    ) -> str:
        body = super().render(users, formatter)
        return f"name,email\n{body}"


def create_report_builder() -> CsvReportBuilder:
    return CsvReportBuilder()


@traced
def generate_report(repository: UserRepository) -> str:
    users = sorted(repository.list_users(), key=presentation.user_sort_key)
    return create_report_builder().render(users, presentation.format_user)


def preview_user(user: User) -> str:
    formatter = presentation.format_user
    add_prefix = presentation.make_prefixer("Preview")
    return add_prefix(formatter(user))
