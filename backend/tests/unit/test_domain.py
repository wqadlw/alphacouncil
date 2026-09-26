"""Unit tests for :mod:`alphacouncil.models.domain`."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from alphacouncil.models.domain import (
    Citation,
    FinancialItem,
    Quote,
    RecallRoute,
    ResearchReport,
    ResearchRequest,
    RetrievedDoc,
    StatementType,
)

pytestmark = pytest.mark.unit


class TestQuote:
    """Price bars must be internally consistent and immutable."""

    def test_valid_bar_is_accepted(self, sample_quote: Quote) -> None:
        assert sample_quote.is_valid_bar() is True
        assert sample_quote.code == "600519"

    def test_inverted_high_low_is_flagged_invalid(self) -> None:
        bar = Quote(
            code="600519",
            trade_date=date(2026, 9, 24),
            open=1500.0,
            high=1400.0,
            low=1600.0,
            close=1510.0,
            volume=1.0,
            amount=1.0,
            source="fixture",
            fetched_at=datetime(2026, 9, 25),
        )

        assert bar.is_valid_bar() is False

    def test_negative_price_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Quote(
                code="600519",
                trade_date=date(2026, 9, 24),
                open=-1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
                amount=1.0,
                source="fixture",
                fetched_at=datetime(2026, 9, 25),
            )

    def test_model_is_immutable(self, sample_quote: Quote) -> None:
        with pytest.raises(ValidationError):
            sample_quote.close = 9999.0  # type: ignore[misc]

    def test_traceability_fields_are_required(self) -> None:
        with pytest.raises(ValidationError):
            Quote(  # type: ignore[call-arg]
                code="600519",
                trade_date=date(2026, 9, 24),
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
                amount=1.0,
            )


class TestRetrievedDoc:
    """Retrieved documents must carry provenance for citation (spec 002 FR-12)."""

    def test_route_ranks_are_recorded(self, sample_docs: list[RetrievedDoc]) -> None:
        doc = sample_docs[0]

        assert doc.route_ranks[RecallRoute.DENSE] == 1
        assert doc.route_ranks[RecallRoute.SPARSE] == 3

    def test_non_positive_rank_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 1"):
            RetrievedDoc(
                doc_id="doc-x",
                content="content",
                source="src",
                route_ranks={RecallRoute.DENSE: 0},
            )

    def test_source_is_required(self) -> None:
        with pytest.raises(ValidationError):
            RetrievedDoc(doc_id="doc-x", content="content")  # type: ignore[call-arg]

    def test_empty_content_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RetrievedDoc(doc_id="doc-x", content="", source="src")


class TestResearchModels:
    """Request and report contracts."""

    def test_query_too_short_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResearchRequest(query="x")

    def test_report_without_citations_is_constructible(self) -> None:
        report = ResearchReport(
            query="Is margin expanding?",
            summary="Insufficient evidence.",
            citations=[],
            generated_at=datetime(2026, 9, 25),
        )

        assert report.citations == []

    def test_citation_requires_verbatim_snippet(self) -> None:
        with pytest.raises(ValidationError):
            Citation(doc_id="doc-a", source="report.pdf", snippet="")

    def test_negative_cost_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResearchReport(
                query="q",
                summary="s",
                cost_usd=-0.01,
                generated_at=datetime(2026, 9, 25),
            )


class TestFinancialItem:
    """Financial line items."""

    def test_statement_type_must_be_known(self) -> None:
        item = FinancialItem(
            code="600519",
            report_date=date(2026, 6, 30),
            statement_type=StatementType.INCOME,
            item="revenue",
            value=1.0,
            source="fixture",
            fetched_at=datetime(2026, 9, 25),
        )

        assert item.statement_type is StatementType.INCOME

    def test_unknown_statement_type_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FinancialItem(
                code="600519",
                report_date=date(2026, 6, 30),
                statement_type="profit_and_loss",  # type: ignore[arg-type]
                item="revenue",
                value=1.0,
                source="fixture",
                fetched_at=datetime(2026, 9, 25),
            )
