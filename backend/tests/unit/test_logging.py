"""Unit tests for :mod:`alphacouncil.core.logging`."""

from __future__ import annotations

import io
import json
import logging

import pytest

from alphacouncil.core.logging import configure_logging, get_logger

pytestmark = pytest.mark.unit


class TestConfigureLogging:
    """The logging setup must produce machine-readable output."""

    def test_json_output_contains_event_and_context(self) -> None:
        stream = io.StringIO()
        configure_logging(level="INFO", json_output=True, stream=stream, force=True)

        get_logger("test").info("quote_fetched", code="600519", rows=1250)

        payload = json.loads(stream.getvalue().strip())
        assert payload["event"] == "quote_fetched"
        assert payload["code"] == "600519"
        assert payload["rows"] == 1250
        assert payload["level"] == "info"

    def test_json_output_includes_iso_timestamp(self) -> None:
        stream = io.StringIO()
        configure_logging(level="INFO", json_output=True, stream=stream, force=True)

        get_logger("test").info("tick")

        payload = json.loads(stream.getvalue().strip())
        assert "timestamp" in payload
        assert "T" in payload["timestamp"]

    def test_console_output_is_not_json(self) -> None:
        stream = io.StringIO()
        configure_logging(level="INFO", json_output=False, stream=stream, force=True)

        get_logger("test").info("human_readable")

        assert "human_readable" in stream.getvalue()

    def test_level_filters_lower_severity(self) -> None:
        stream = io.StringIO()
        configure_logging(level="WARNING", json_output=True, stream=stream, force=True)
        logger = get_logger("test")

        logger.debug("should_be_dropped")
        logger.info("also_dropped")
        logger.warning("kept")

        output = stream.getvalue()
        assert "should_be_dropped" not in output
        assert "also_dropped" not in output
        assert "kept" in output

    def test_unknown_level_falls_back_to_info(self) -> None:
        stream = io.StringIO()
        configure_logging(level="NOT_A_LEVEL", json_output=True, stream=stream, force=True)

        get_logger("test").info("still_logged")

        assert "still_logged" in stream.getvalue()

    def test_repeated_call_without_force_is_a_noop(self) -> None:
        first = io.StringIO()
        second = io.StringIO()
        configure_logging(level="INFO", json_output=True, stream=first, force=True)

        # Without force, the second call must not reconfigure the sink.
        configure_logging(level="INFO", json_output=True, stream=second, force=False)

        get_logger("test").info("routed_to_first")
        assert "routed_to_first" in first.getvalue()
        assert "routed_to_first" not in second.getvalue()

    def test_stdlib_logging_is_routed_to_the_same_sink(self) -> None:
        stream = io.StringIO()
        configure_logging(level="INFO", json_output=True, stream=stream, force=True)

        logging.getLogger("third.party").warning("from_stdlib")

        assert "from_stdlib" in stream.getvalue()


class TestGetLogger:
    """Logger retrieval must be safe with and without a name."""

    def test_named_logger_binds_the_name(self) -> None:
        stream = io.StringIO()
        configure_logging(level="INFO", json_output=True, stream=stream, force=True)

        get_logger("alphacouncil.retrieval").info("named")

        payload = json.loads(stream.getvalue().strip())
        assert payload["logger"] == "alphacouncil.retrieval"

    def test_unnamed_logger_still_logs(self) -> None:
        stream = io.StringIO()
        configure_logging(level="INFO", json_output=True, stream=stream, force=True)

        get_logger().info("anonymous")

        assert "anonymous" in stream.getvalue()
