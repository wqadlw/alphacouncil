"""Make this process's own console output survive whatever console it lands on.

**The defect this exists to prevent** (``regressions/0004``): the developer tools
print a tick and a cross as their pass/fail markers, and on a Chinese Windows
console ``sys.stdout.encoding`` is ``gbk`` — which has neither character, and
whose default ``errors='strict'`` turns that into a ``UnicodeEncodeError``
*mid-report*. ``scripts/dev.py`` therefore printed ``ran 10 · passed 10 ·
failed 0`` and then exited **1** from an unhandled exception. The gate had gone
green and the gate runner said it failed.

Verified per character against a real GBK stream, 2026-09-28:

===============  ==========================================
character        writing it to a GBK stream
===============  ==========================================
``✓`` U+2713     ``UnicodeEncodeError``
``✗`` U+2717     ``UnicodeEncodeError``
``⚠`` U+26A0     ``UnicodeEncodeError``
``→`` U+2192     fine
``·`` U+00B7     fine
===============  ==========================================

So the fix is not "pick different markers" — it is that *this process* chooses
its own output encoding, instead of inheriting whatever the console happened to
report. Then a tool prints a tick on a cp936 console, on a UTF-8 CI runner, and
on a pipe redirected to a file, and it means the same thing in all three.

**Why ``errors="replace"`` and not just UTF-8**: UTF-8 can encode every
character these tools use, so the flag should never fire. It is there so that
the day something genuinely cannot be encoded, a *checker* degrades to a
question mark instead of dying — see "Why silence is correct" below.

**Why stderr is reconfigured too**: ``sys.stderr`` is not the problem — Python
gives it ``backslashreplace`` — but the consequence is worse than a crash. A
``✓`` it cannot encode is written as the six literal characters ``\\u2713``,
which is what ``python -m checks --strict`` printed on this machine before the
fix. It exits 0, so nothing goes red; the PASS marker just quietly stops being a
tick. An exit code that is right and an output that lies is harder to notice than
a crash.
"""

from __future__ import annotations

import sys
from typing import TextIO

__all__ = ["use_utf8"]


def use_utf8() -> None:
    """Make this process's own stdout and stderr UTF-8.

    Call once, first thing in a tool's ``main()``, before anything is printed.
    Safe to call twice, safe to call when the streams have been replaced by
    something that cannot be reconfigured, and safe when there is no console at
    all.
    """
    for stream in (sys.stdout, sys.stderr):
        _reconfigure(stream)


def _reconfigure(stream: TextIO | None) -> None:
    """Put one stream into UTF-8, or leave it alone if that is not possible.

    ### Why silence is correct here

    The constitution's "errors must be explicit" rule is about *business* logic
    failing quietly. This is not that: the verdict of a gate is carried by its
    **exit code**, not by whether a tick got drawn. A tool that refuses to run
    because it could not draw a marker is strictly worse than one that runs and
    draws a question mark — it is the exact failure this module was added to fix,
    just wearing a different hat. So every branch below returns, and the reason
    each one exists is written next to it rather than left to be rediscovered.

    The three cases that must not raise:

    ``None``
        ``sys.stdout`` is ``None`` on Windows when the process was started by
        ``pythonw.exe`` with no console. This project ships as a pywebview
        desktop application, so that is a path it will eventually take.
    no ``reconfigure`` attribute
        pytest's capture objects and some IDE stream wrappers are not
        ``io.TextIOWrapper`` and have no such method.
    already closed
        ``reconfigure`` raises ``ValueError`` on a closed stream.
    """
    if stream is None:
        return
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        # `io.UnsupportedOperation` subclasses both of these, so naming it
        # separately would be a redundant except clause (flake8-bugbear B014).
        return
