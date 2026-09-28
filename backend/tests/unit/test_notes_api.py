"""The notes API (spec 026) — the path a note actually travels.

Every test here is about a promise the HTTP surface makes, not about the
repository, which `test_notes.py` already covers. The two that matter most:

* a note goes in **with no source and no ticker** — the whole reason this feature
  exists, and the thing that would silently stop being true if someone tightened
  the request schema;
* a card posted with no source is still refused, **on the same running server**,
  which is the only way to show the provenance rule survived a new endpoint
  being added next to it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A client over the isolated database, with migrations already applied.

    ⭐ The `with` matters: `create_app()` installs a lifespan that runs migrations,
    and a bare `TestClient(app)` skips it — so every request would then hit a
    database with no `notes` table and answer "no such table", which looks like a
    routing bug and is not one.
    """
    with TestClient(create_app()) as test_client:
        yield test_client


def _post_note(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "流动性收紧时周期股先跌",
        "body": "## 观察\n\n- 2026-08 利率上行\n- 成长股滞后 3 周",
    }
    payload.update(overrides)
    response = client.post("/api/v1/notes", json=payload)
    assert response.status_code == 201, response.text
    parsed: dict[str, Any] = response.json()
    return parsed


class TestRecording:
    def test_a_note_with_no_source_and_no_ticker_is_accepted(
        self, client: TestClient
    ) -> None:
        """⭐ The feature. Everything else in this file is detail."""
        created = _post_note(client)
        assert created["tags"] == []
        assert created["symbols"] == []
        assert created["links"] == []
        assert created["as_of"] is None
        assert created["id"].startswith("note_")

    def test_the_markdown_comes_back_byte_for_byte(self, client: TestClient) -> None:
        """Whitespace, indentation and punctuation are the user's own."""
        body = "# 标题\n\n- 一\n- 二\n\n  两格缩进\n\n**不加空格**的收尾"
        created = _post_note(client, body=body)
        fetched = client.get(f"/api/v1/notes/{created['id']}").json()
        assert fetched["body"] == body

    def test_a_note_may_carry_tickers(self, client: TestClient) -> None:
        created = _post_note(client, symbols=["600519", "sh000858"])
        assert [s["code"] for s in created["symbols"]] == ["600519", "000858"]

    def test_an_ambiguous_ticker_is_refused_not_guessed(
        self, client: TestClient
    ) -> None:
        """A note misattributed to the wrong exchange is a note that will later
        read as evidence for the wrong argument."""
        response = client.post(
            "/api/v1/notes",
            json={"title": "t", "body": "b", "symbols": ["000001"]},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "DATA_SOURCE_TICKER_AMBIGUOUS"

    def test_a_blank_title_is_refused(self, client: TestClient) -> None:
        response = client.post("/api/v1/notes", json={"title": "   ", "body": "b"})
        assert response.status_code == 400
        assert response.json()["code"] == "NOTE_TITLE_REQUIRED"

    def test_a_client_supplied_id_is_refused(self, client: TestClient) -> None:
        """Back-dating a record is the thing `extra="forbid"` exists for."""
        response = client.post(
            "/api/v1/notes",
            json={"id": "note_1", "title": "t", "body": "b"},
        )
        assert response.status_code == 422


class TestTheProvenanceRuleSurvived:
    def test_a_card_still_may_not_be_written_without_a_source(
        self, client: TestClient
    ) -> None:
        """⭐ Adding a notes endpoint must not have relaxed anything.

        Same server, same moment: a note with no source succeeds, a card with no
        source does not. That pairing is the only honest way to state the rule.
        """
        _post_note(client)

        def post(url: str, title: str) -> Any:
            return client.post(
                "/api/v1/cards",
                json={
                    "content": "高端白酒提价能力持续",
                    "claim_type": "supporting",
                    "source_url": url,
                    "source_title": title,
                },
            )

        # Two layers, and the distinction is worth stating rather than collapsing
        # into "it was rejected": an **empty** string never reaches the domain at
        # all — the request schema refuses it with a 422, because there is no value
        # to check. A string that is present but unusable (blank, or not http/https)
        # gets past the schema and is then refused by the domain, with the code
        # that names the rule.
        assert post("", "").status_code == 422
        assert post("   ", "t").json()["code"] == "CARD_SOURCE_URL_REQUIRED"
        assert post("ftp://x", "t").json()["code"] == "CARD_SOURCE_URL_REQUIRED"

    def test_a_card_with_a_real_source_still_works(self, client: TestClient) -> None:
        """The other half: the rule is a *requirement*, not a blanket refusal."""
        response = client.post(
            "/api/v1/cards",
            json={
                "content": "高端白酒提价能力持续",
                "claim_type": "supporting",
                "source_url": "https://example.com/r",
                "source_title": "白酒渠道调研",
            },
        )
        assert response.status_code == 201


class TestTagsAndLinks:
    def test_tags_can_be_added_and_removed(self, client: TestClient) -> None:
        created = _post_note(client, tags=["宏观", " 估值 "])
        assert created["tags"] == ["估值", "宏观"]  # trimmed, sorted

        note_id = created["id"]
        after = client.post(f"/api/v1/notes/{note_id}/tags", json={"tag": "利率"})
        assert "利率" in after.json()["tags"]

        after = client.delete(f"/api/v1/notes/{note_id}/tags/利率")
        assert "利率" not in after.json()["tags"]

    def test_a_comma_in_a_tag_is_refused(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/notes", json={"title": "t", "body": "b", "tags": ["宏观,估值"]}
        )
        assert response.status_code == 400
        assert response.json()["code"] == "NOTE_TAG_INVALID"

    def test_a_tag_filter_is_exact(self, client: TestClient) -> None:
        """⭐ `LIKE '%宏观%'` would return 宏观债 too, and the filtered list would
        then silently omit a note the reader can see unfiltered."""
        broad = _post_note(client, title="宏观", body="关于宏观", tags=["宏观"])
        _post_note(client, title="宏观债", body="关于宏观债", tags=["宏观债"])

        found = client.get("/api/v1/notes", params={"tag": "宏观"}).json()
        assert [n["id"] for n in found] == [broad["id"]]

    def test_every_tag_in_use_is_listed(self, client: TestClient) -> None:
        _post_note(client, title="a", body="b", tags=["宏观"])
        _post_note(client, title="c", body="d", tags=["估值"])
        assert client.get("/api/v1/notes/tags").json() == ["估值", "宏观"]

    def test_a_link_to_a_missing_target_is_refused(self, client: TestClient) -> None:
        """The check SQLite cannot do, made visible at the edge."""
        response = client.post(
            "/api/v1/notes",
            json={
                "title": "t",
                "body": "b",
                "links": [{"to_kind": "card", "to_id": "card_9999999999999"}],
            },
        )
        assert response.status_code == 400
        assert response.json()["code"] == "NOTE_LINK_TARGET_UNKNOWN"

    def test_a_note_can_link_to_a_card_and_the_link_is_returned(
        self, client: TestClient
    ) -> None:
        card = client.post(
            "/api/v1/cards",
            json={
                "content": "渠道库存是白酒先行指标",
                "claim_type": "supporting",
                "source_url": "https://example.com/r",
                "source_title": "白酒渠道调研",
            },
        )
        assert card.status_code == 201, card.text
        card_id = card.json()["id"]

        created = _post_note(
            client, links=[{"to_kind": "card", "to_id": card_id}]
        )
        assert created["links"] == [{"to_kind": "card", "to_id": card_id}]


class TestEditingAndAbsence:
    def test_a_note_can_be_edited_and_created_at_does_not_move(
        self, client: TestClient
    ) -> None:
        """A note is working text; a card is a signed claim. That is why one has a
        PATCH and the other does not."""
        created = _post_note(client, body="第一版")
        response = client.patch(
            f"/api/v1/notes/{created['id']}", json={"body": "第二版"}
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["body"] == "第二版"
        assert updated["created_at"] == created["created_at"]
        assert updated["title"] == created["title"]

    def test_an_edit_cannot_blank_the_body(self, client: TestClient) -> None:
        created = _post_note(client)
        response = client.patch(f"/api/v1/notes/{created['id']}", json={"body": "  "})
        assert response.status_code == 400
        assert response.json()["code"] == "NOTE_BODY_BLANK"

    def test_a_missing_note_is_a_404_not_an_empty_note(self, client: TestClient) -> None:
        """A caller that reads "absent" as "empty" would render a blank page for a
        deleted id and call it an empty vault."""
        response = client.get("/api/v1/notes/note_9999999999999")
        assert response.status_code == 404

    def test_an_empty_vault_lists_nothing(self, client: TestClient) -> None:
        assert client.get("/api/v1/notes").json() == []
