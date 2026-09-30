"""``python -m alphacouncil.notify send_due`` — say what is due, once (spec 044).

## ⭐ Why a command and not a daemon

There is **no runtime agent** (ADR-0027: LangGraph and fastmcp are adopted and not built),
so 「check on a schedule」 needs a background process — ⭐ which means scheduling, lifecycle,
logging, and a new failure mode, all for a feature whose honest scope is one message.

So it is a command. ⭐ Zero new dependencies, zero background threads, fully testable, ⭐
and it promises exactly what it can deliver: **「你跑了它,它就说」**. ⭐ A Windows scheduled
task is how you *use* this, and that is a deployment decision rather than a code one.

## ⭐ What it does and does not print

It prints one line — the :meth:`~alphacouncil.notify.dispatch.SendReport.summary` — and
exits 0 whether or not anything was delivered. ⭐ A non-zero exit on 「nothing to say」 would
make a scheduled task report a failure every quiet day, ⭐ and a failure the reader cannot
act on is worse than no signal.
"""

from __future__ import annotations

import sys
from typing import Annotated

import structlog
from pydantic import SecretStr

from alphacouncil.core.config import Settings, get_settings
from alphacouncil.notify.dispatch import send_due_criteria
from alphacouncil.notify.webhook import ChannelConfig
from alphacouncil.storage import db as storage_db
from alphacouncil.storage import migrate

log = structlog.get_logger(__name__)


def _channel(settings: Settings) -> ChannelConfig | None:
    """The webhook endpoint, or ``None`` when the reader configured none.

    ⭐ A :class:`~pydantic.SecretStr`, and the **whole URL** is the secret: ⭐ a 飞书 hook
    embeds its token in the path (``/hook/xxxxxxxx``), ⭐ so splitting base and token would
    put the token in a plain field that anything may print. ⭐ This is the same shape the
    LLM keys already use in :mod:`alphacouncil.core.config` — 环境变量 + ``SecretStr``,
    never a file in the repository.
    """
    url: SecretStr | None = getattr(settings, "webhook_url", None)
    if url is None or not url.get_secret_value().strip():
        return None
    return ChannelConfig(url=url.get_secret_value().strip())


def _attention(settings: Settings) -> list[dict[str, object]]:
    """Today's attention rows, as the API shaped them.

    ⭐ Read through the **route's own function**, not by re-querying: ⭐ ``/api/v1/today``
    already computed the sentences and the ``adjudicable`` flags, ⭐ and recomputing them
    here would be a second implementation of 「什么状态可以据此行动」 — ⭐ which is the
    mistake `spec 040`'s own notes call out one layer down.
    """
    from alphacouncil.api.routes import today as today_route
    from alphacouncil.providers import default_router

    router = default_router()
    connection = storage_db.connect(settings.database_path)
    try:
        payload = today_route.today(connection, router)
    finally:
        connection.close()
    return [item.model_dump(mode="json") for item in payload.attention]


def _prepare(database_path: object) -> None:
    """Bring the database to the newest schema, so a fresh install can notify at all.

    ⭐ ⭐ **This runs the migrations on every invocation**, which looks wrong and is not:
    ⭐ this is a command a person (or a scheduled task) runs, ⭐ there is no server start
    to hang the migration off, ⭐ and 「表还没建所以通知不了」 is a failure mode a user hits
    exactly once, on day one, with no explanation.

    ⭐ The upgrade is cheap after the first run — `migrate.apply` reports an empty
    ``applied`` and takes a snapshot only when there is something to do.
    """
    connection = storage_db.connect_for_migration(database_path)  # type: ignore[arg-type]
    try:
        migrate.apply(connection, database_path=database_path)  # type: ignore[arg-type]
    finally:
        connection.close()


def main(argv: Annotated[list[str] | None, None] = None) -> int:
    """Entry point. Returns the process exit code."""
    from _console import use_utf8

    use_utf8()
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in {"-h", "--help"}:
        print("用法: python -m alphacouncil.notify send_due")
        return 0
    if args and args[0] != "send_due":
        print(f"未知子命令: {args[0]}")
        return 2

    settings = get_settings()
    _prepare(settings.database_path)

    connection = storage_db.connect(settings.database_path)
    try:
        report = send_due_criteria(connection, _attention(settings), config=_channel(settings))
    finally:
        connection.close()

    print(report.summary())
    return 0


__all__ = ["main"]
