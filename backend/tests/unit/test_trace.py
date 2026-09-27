"""The trace writer (spec 011) — replayable records that never lie or leak.

Marked ``unit``: traces land in a temporary directory (wired through
``ALPHACOUNCIL_TRACES_DIR``), clocks are real but durations only need to be
*positive*, and the network is nowhere. The assertions that matter most are
the negative ones: no request body text ever appears in a trace file, and a
broken trace destination never breaks the request it was tracing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.trace import TraceWriter, current_trace, set_current_trace
from alphacouncil.models.market import DataResult, Market, Quote, RealtimeQuote, Symbol
from alphacouncil.providers.base import Dataset, ProviderCapabilities
from alphacouncil.providers.router import MarketDataRouter

pytestmark = pytest.mark.unit

STAMP = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
MOUTAI = Symbol(market=Market.SH, code="600519")

SECRET_TEXT = "毛利率连续三年高于 90%，这是绝不能进 trace 的原文"


def ok_result() -> DataResult[RealtimeQuote]:
    return DataResult.ok(
        RealtimeQuote.model_validate(
            {
                "symbol": MOUTAI,
                "price": 1237.0,
                "prev_close": 1251.0,
                "open": 1250.0,
                "high": 1255.0,
                "low": 1230.0,
                "volume": 2_400_000.0,
                "amount": 2.97e9,
                "quoted_at": STAMP,
                "source": "stub",
                "fetched_at": STAMP,
            }
        ),
        source="stub",
        fetched_at=STAMP,
    )


class _Healthy:
    name = "stub"
    capabilities = ProviderCapabilities(datasets=frozenset({Dataset.REALTIME}))

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        return ok_result()

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: object = None,
        end: object = None,
    ) -> DataResult[list[Quote]]:
        raise AssertionError("not used here")


def lines_of(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def all_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.jsonl"))


def app_with_traces_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FastAPI:
    """An app whose traces land in a known temporary directory."""
    monkeypatch.setenv("ALPHACOUNCIL_TRACES_DIR", str(tmp_path / "traces"))
    from alphacouncil.core.config import get_settings

    get_settings.cache_clear()
    return create_app()


# ---------------------------------------------------------------------------
# layout and fields
# ---------------------------------------------------------------------------


def test_one_trace_is_one_dated_file_with_a_header_and_observations(tmp_path: Path) -> None:
    writer = TraceWriter(tmp_path / "traces")

    with (
        writer.start("GET /api/v1/today") as trace,
        trace.observation("provider:stub", meta={"dataset": "realtime"}),
    ):
        pass

    files = all_files(tmp_path / "traces")
    assert len(files) == 1
    records = lines_of(files[0])
    assert records[0]["kind"] == "trace"
    assert records[0]["name"] == "GET /api/v1/today"
    observations = [r for r in records if r["kind"] == "observation"]
    assert len(observations) == 1
    observation = observations[0]
    assert observation["trace_id"] == records[0]["id"]
    assert observation["name"] == "provider:stub"
    assert observation["status"] == "ok"
    assert observation["duration_ms"] > 0
    assert observation["token_count"] is None and observation["cost_usd"] is None


def test_observations_are_appended_never_rewritten(tmp_path: Path) -> None:
    """Two writes to the same trace must both survive — append-only means the
    first line's bytes are still there after the second write."""
    writer = TraceWriter(tmp_path / "traces")
    trace = writer.start("run")

    with trace.observation("step-1"):
        pass
    first_snapshot = trace._file.read_bytes()
    with trace.observation("step-2"):
        pass

    assert trace._file.read_bytes().startswith(first_snapshot)
    assert [r["name"] for r in lines_of(trace._file) if r["kind"] == "observation"] == [
        "step-1",
        "step-2",
    ]


def test_two_runs_land_in_two_files(tmp_path: Path) -> None:
    writer = TraceWriter(tmp_path / "traces")
    for name in ("run-a", "run-b"):
        with writer.start(name) as trace, trace.observation("step"):
            pass

    files = all_files(tmp_path / "traces")
    assert len(files) == 2


def test_a_score_lands_in_the_scores_file(tmp_path: Path) -> None:
    writer = TraceWriter(tmp_path / "traces")
    trace = writer.start("run")
    trace.score("eval_pass", 1.0, comment="smoke")

    scores = list((tmp_path / "traces" / "scores").glob("*.jsonl"))
    assert len(scores) == 1
    record = lines_of(scores[0])[0]
    assert record["kind"] == "score"
    assert record["trace_id"] == trace.id
    assert record["value"] == 1.0


def test_every_line_is_valid_json(tmp_path: Path) -> None:
    writer = TraceWriter(tmp_path / "traces")
    with writer.start("run") as trace, trace.observation("step"):
        pass
    trace.score("s", 0.5)

    for file in all_files(tmp_path / "traces"):
        for line in file.read_text(encoding="utf-8").splitlines():
            json.loads(line)


# ---------------------------------------------------------------------------
# the request path
# ---------------------------------------------------------------------------


def test_a_request_leaves_a_trace_with_status_and_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALPHACOUNCIL_TRACES_DIR", str(tmp_path / "traces"))
    app = app_with_traces_in(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    files = all_files(tmp_path / "traces")
    assert len(files) == 1
    records = lines_of(files[0])
    assert records[0]["name"] == "GET /health"
    http_steps = [r for r in records if r["kind"] == "observation" and r["name"] == "http"]
    assert len(http_steps) == 1
    assert http_steps[0]["meta"]["http_status"] == 200
    assert http_steps[0]["duration_ms"] > 0


def test_decisions_leave_no_original_text_in_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The audit says what was done, never what was said (constitution 6.3).

    A decision is recorded through the API with text that must never reach the
    traces directory; the trace for that very request exists, carrying status
    and duration instead of the reader's words.
    """
    monkeypatch.setenv("ALPHACOUNCIL_TRACES_DIR", str(tmp_path / "traces"))
    app = app_with_traces_in(monkeypatch, tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/decisions",
            json={
                "ticker": "600519",
                "action": "buy",
                "rationale": SECRET_TEXT,
                "counter_evidence": SECRET_TEXT,
                "kill_criteria": [
                    {
                        "metric": "revenue_yoy",
                        "operator": "<",
                        "threshold": 0.55,
                        "as_of": "2026-12-31",
                    }
                ],
            },
        )
        assert response.status_code == 201, response.text

    raw = "\n".join(file.read_text(encoding="utf-8") for file in all_files(tmp_path / "traces"))
    assert SECRET_TEXT not in raw
    assert "POST /api/v1/decisions" in raw


# ---------------------------------------------------------------------------
# the router hook
# ---------------------------------------------------------------------------


def test_a_provider_fetch_becomes_an_observation(tmp_path: Path) -> None:
    """Inside a trace, the router's upstream calls are on the record: which
    source, which dataset, which of the four states, how long."""
    writer = TraceWriter(tmp_path / "traces")
    router = MarketDataRouter([_Healthy()], cache=None, tracer=writer)

    trace = writer.start("probe")
    set_current_trace(trace)
    try:
        with trace.observation("request"):
            result = router.get_realtime(MOUTAI)
    finally:
        set_current_trace(None)

    assert result.status.value == "ok"
    observations = [r for r in lines_of(trace._file) if r["kind"] == "observation"]
    provider_obs = next(r for r in observations if r["name"] == "provider:stub")
    assert provider_obs["meta"]["dataset"] == "realtime"
    assert provider_obs["meta"]["symbol"] == "600519.SH"
    assert provider_obs["status"] == "ok"


def test_fetching_without_a_trace_still_works(tmp_path: Path) -> None:
    """No trace bound to the context → the hook no-ops and the fetch succeeds."""
    assert current_trace() is None
    router = MarketDataRouter([_Healthy()], cache=None, tracer=TraceWriter(tmp_path / "traces"))

    result = router.get_realtime(MOUTAI)

    assert result.status.value == "ok"
    assert list((tmp_path / "traces").rglob("*.jsonl")) == []


def test_a_broken_trace_destination_never_breaks_the_run(tmp_path: Path) -> None:
    """The destination root sits *inside* a plain file; creating directories
    under it must fail — and the writer must swallow that instead of raising
    into the request."""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    writer = TraceWriter(blocked / "traces")

    trace = writer.start("run")
    with trace.observation("step"):
        pass

    assert all_files(blocked / "traces") == []
