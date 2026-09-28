"""Regression tests for ``0004`` — the gates cannot print on a Chinese console.

The whole file exists because of one fact about this machine: a Chinese Windows
console reports ``sys.stdout.encoding == 'gbk'``, and the developer tools mark
their verdicts with ``✓`` / ``✗`` / ``⚠``, none of which GBK can encode. With
``sys.stdout``'s default ``errors='strict'`` that is a ``UnicodeEncodeError``
part-way through the report — and in ``scripts/dev.py`` it landed *after* the
"ran 10 · passed 10" line, so a fully green run exited **1**.

Two things make these tests worth having rather than trusting a manual run:

1. **The failure is reproduced in-process**, against a ``BytesIO`` wrapped in a
   real ``TextIOWrapper(encoding="gbk")``. It therefore fails on a UTF-8 CI
   runner too. A test that only breaks on one developer's machine is a test CI
   cannot hold you to.
2. **Every expected value is a literal.** ``regressions/README.md`` rule 1: a
   test that imports its markers from the code under test cannot tell you
   whether those characters are encodable. So ``"\\u2713"`` appears here as an
   escape, spelled out, and never as an import.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Imported as top-level modules, exactly as `python scripts/check_licenses.py`
# imports them: `pyproject.toml` puts `scripts/` on `pythonpath` so this is the
# *same* import the tool does at runtime, not a second, more forgiving one. A
# test that imported them as `scripts.check_licenses` would exercise a path the
# tools never take.
import _console as console
import check_licenses
import pytest

if TYPE_CHECKING:
    pass

BACKEND = Path(__file__).resolve().parents[2]

#: Environment variables that would decide a child process's encoding for us.
_ENCODING_VARS = ("PYTHONIOENCODING", "PYTHONUTF8")

#: A tick. Not in GBK. Written as an escape so the reason survives any editor
#: that might normalise the file's encoding — a literal ``✓`` in a test file is
#: one re-save away from becoming three question marks that pass for a test.
TICK = "\u2713"
CROSS = "\u2717"
WARNING_SIGN = "\u26a0"


def gbk_stream() -> tuple[io.TextIOWrapper, io.BytesIO]:
    """A stdout that behaves exactly like this machine's console.

    ``gbk`` because that is what cp936 reports; ``strict`` because that is
    ``sys.stdout``'s default and the whole defect is a consequence of it.

    Returns the buffer alongside so a test can read back the *bytes* actually
    written — asserting on the text layer would pass even if the encoding were
    wrong in a way `getvalue` hides.
    """
    buffer = io.BytesIO()
    return io.TextIOWrapper(buffer, encoding="gbk", errors="strict"), buffer


class TestThePremiseIsReal:
    """Pin *why* the fix is needed, so a future 'cleanup' cannot dismiss it."""

    def test_gbk_cannot_encode_a_tick_before_the_fix(self) -> None:
        stream, _buffer = gbk_stream()
        with pytest.raises(UnicodeEncodeError):
            stream.write(TICK)

    def test_gbk_can_encode_the_characters_the_gates_get_right(self) -> None:
        """`·` and `→` are in GBK — which is why only the markers broke."""
        stream, _buffer = gbk_stream()
        stream.write("\u00b7\u2192")
        stream.flush()


class TestUseUtf8:
    def test_a_tick_survives_a_gbk_stream(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stream, buffer = gbk_stream()
        monkeypatch.setattr(sys, "stdout", stream)
        console.use_utf8()
        stream.write(TICK)
        stream.flush()
        assert buffer.getvalue().decode("utf-8") == TICK

    def test_every_verdict_marker_survives(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stream, buffer = gbk_stream()
        monkeypatch.setattr(sys, "stdout", stream)
        console.use_utf8()
        stream.write(f"{TICK}{CROSS}{WARNING_SIGN}")
        stream.flush()
        assert buffer.getvalue().decode("utf-8") == f"{TICK}{CROSS}{WARNING_SIGN}"

    def test_stderr_is_reconfigured_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`checks` writes to stderr, where a bad marker becomes a literal escape.

        Python gives stderr ``backslashreplace``, so this never raised — it
        printed the six characters ``\\u2713`` and exited 0. Right exit code,
        output that lies.
        """
        stream, buffer = gbk_stream()
        monkeypatch.setattr(sys, "stderr", stream)
        console.use_utf8()
        stream.write(TICK)
        stream.flush()
        assert buffer.getvalue().decode("utf-8") == TICK

    def test_a_missing_console_is_tolerated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`sys.stdout is None` under `pythonw.exe` — a path this project will take.

        It ships as a pywebview desktop app, so a console-less launch is not
        hypothetical.
        """
        monkeypatch.setattr(sys, "stdout", None)
        monkeypatch.setattr(sys, "stderr", None)
        console.use_utf8()

    def test_a_stream_that_cannot_be_reconfigured_is_tolerated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pytest's capture object has no `reconfigure`; it must not blow up."""
        monkeypatch.setattr(sys, "stdout", object())
        console.use_utf8()

    def test_a_closed_stream_is_tolerated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stream, _buffer = gbk_stream()
        stream.close()
        monkeypatch.setattr(sys, "stdout", stream)
        console.use_utf8()

    def test_calling_it_twice_is_harmless(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stream, buffer = gbk_stream()
        monkeypatch.setattr(sys, "stdout", stream)
        console.use_utf8()
        console.use_utf8()
        stream.write(TICK)
        stream.flush()
        assert buffer.getvalue().decode("utf-8") == TICK


class TestTheLicenceGate:
    """`check_licenses.py` had a *latent* crash on the branch that matters.

    Its `✗` and `⚠` are printed only when a copyleft dependency is found — and
    the day one is, this tool would raise `UnicodeEncodeError` instead of
    reporting the licence problem it exists to report. The branch was
    unreachable when the defect was found (`ok=42 fail=0`), so it is induced
    here rather than hoped for.

    Note what these tests do **not** do: they never call ``use_utf8()``. The fix
    has to be inside ``check_licenses.main()`` or these stay red — a test that
    applies the fix itself would pass whether or not the tool ever did.
    """

    def _install_finding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_scan() -> list[check_licenses.Finding]:
            return [
                check_licenses.Finding(
                    name="some-copyleft-thing",
                    version="1.2.3",
                    licence="GPL-3.0",
                    verdict=check_licenses.Verdict.FAIL,
                )
            ]

        monkeypatch.setattr(check_licenses, "scan", fake_scan)

    def test_a_copyleft_finding_is_reported_rather_than_crashing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._install_finding(monkeypatch)
        stream, buffer = gbk_stream()
        monkeypatch.setattr(sys, "stdout", stream)
        assert check_licenses.main() == 1
        stream.flush()
        rendered = buffer.getvalue().decode("utf-8")
        assert CROSS in rendered
        assert "some-copyleft-thing" in rendered

    def test_a_clean_scan_still_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(check_licenses, "scan", list)
        stream, buffer = gbk_stream()
        monkeypatch.setattr(sys, "stdout", stream)
        assert check_licenses.main() == 0
        stream.flush()
        assert "ok=0" in buffer.getvalue().decode("utf-8")


class TestTheRealProcess:
    """A real console, a real process, a real exit code.

    Everything above reconfigures a stream the test owns. Only this class checks
    the thing the defect was actually about: *the tool as shipped, deciding its
    own encoding*. So these run the real entry points, and ``PYTHONIOENCODING``
    is how CPython decides a child process's encoding — which is what makes them
    reproducible on a UTF-8 CI runner too, instead of only on this machine.
    """

    def _run_with_a_gbk_console(self, argv: list[str]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(  # noqa: S603
            argv,
            cwd=BACKEND,
            capture_output=True,
            check=False,
            env={**_clean_env(), "PYTHONIOENCODING": "gbk"},
        )

    def test_the_licence_gate_exits_zero_from_a_real_process(self) -> None:
        completed = self._run_with_a_gbk_console([sys.executable, "scripts/check_licenses.py"])
        assert completed.returncode == 0, completed.stderr.decode("gbk", "replace")

    def test_the_static_checks_exit_zero_and_print_a_real_tick(self) -> None:
        completed = self._run_with_a_gbk_console([sys.executable, "-m", "checks", "--strict"])
        assert completed.returncode == 0, completed.stderr.decode("gbk", "replace")
        assert b"\\u2713" not in completed.stderr
        assert TICK.encode() in completed.stderr

    def test_the_gate_runner_reports_success_instead_of_crashing(self) -> None:
        """The reported defect, end to end.

        ``dev.py <gate>`` runs exactly one gate and then the T-19 summary, so
        this is the real `_summarise` on a real GBK console without paying for
        all ten. Before the fix this exited **1** from a `UnicodeEncodeError`
        while the gate itself had passed.
        """
        completed = self._run_with_a_gbk_console(
            [sys.executable, "scripts/dev.py", "check-static"]
        )
        rendered = completed.stdout.decode("utf-8", "replace")
        assert completed.returncode == 0, rendered
        assert TICK in rendered
        assert "ran 1 " in rendered
        assert "UnicodeEncodeError" not in rendered


def _clean_env() -> dict[str, str]:
    """The current environment, minus any variable that would re-force an encoding.

    Without this, a developer's ``PYTHONIOENCODING`` or ``PYTHONUTF8`` would
    quietly decide the answer and the test would stop meaning anything.
    """
    return {key: value for key, value in os.environ.items() if key not in _ENCODING_VARS}
