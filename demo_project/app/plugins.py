"""Known plugin methods resolve; runtime-selected handlers remain unresolved."""

from .models import User
from .validators import validate_name


class Plugin:
    def process(self, user: User) -> User:
        return user


class NormalizeNamePlugin(Plugin):
    def process(self, user: User) -> User:
        user = super().process(user)
        user.name = validate_name(user.name)
        return user


def normalize_user(user: User) -> User:
    plugin = NormalizeNamePlugin()
    handler = plugin.process
    return handler(user)


def invoke_plugin(plugin, user: User) -> User:
    handler = getattr(plugin, "process")
    return handler(user)
