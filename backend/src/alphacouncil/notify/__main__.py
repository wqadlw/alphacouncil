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
from alphacouncil.core.console import use_utf8
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
    # ⭐ From the **package**, not from `scripts/`. ⭐ `scripts/_console.py` is a forwarding
    # import to this same place, ⭐ and the first version of this file reached for the
    # scripts one -- ⭐ which is not on `sys.path` when this runs as `python -m`, ⭐ so the
    # command died with ``ModuleNotFoundError: No module named '_console'`` ⭐ after the
    # missing-`__main__` guard above was fixed. ⭐ Product code importing a dev script is the
    # kind of dependency that only fails when it is actually run.
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


if __name__ == "__main__":
    # ⭐⭐ **This line was missing, and nothing caught it.**
    #
    # ⭐ ``python -m alphacouncil.notify`` **imports** this module — ⭐ it does not call
    # ``main()``. ⭐ Without this block the command exits **0**, prints nothing, and sends
    # nothing, ⭐ which is the worst shape a command can have: ⭐ a scheduled task would
    # report success forever while the reader heard nothing at all.
    #
    # ⭐ And the gate was green throughout, ⭐ because ⭐ **no test ever ran this entry
    # point** — ⭐ the same 「机制齐了但入口没有」 that `spec 020` diagnosed for J3, ⭐ and the
    # reason there is now a test that runs the module as a subprocess.
    #
    # ⭐ One phrase above uses 「但」 where the natural Chinese wants a full-width
    # comma, because `RUF003` rejects that character in a **comment**. ⭐ And the
    # second half is the part worth keeping: ⭐ a comment about avoiding a character
    # cannot quote the character, ⭐ so this note has now failed on that twice, and
    # the only honest way to write it is to describe the character and move on.
    # ⭐ The full-width comma is still everywhere it belongs — this repository's own
    # docs, and every Chinese sentence in them.
    #
    # ⭐ ``sys.exit`` rather than ``SystemExit(main())``: ⭐ it matches the sibling
    # ``alphacouncil/__main__.py``, ⭐ and 「两个入口长得不一样」 is a small thing that costs
    # a reader a minute every time.
    sys.exit(main())


__all__ = ["main"]
