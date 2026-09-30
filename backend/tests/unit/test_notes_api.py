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
        """Sorted, because the create response is now a read of the note.

        It used to be assembled from the draft and so came back in the order the
        caller supplied, while `GET /notes/{id}` ordered them. One note answering
        two ways depending on how you reached it is the hazard the assembly change
        set out to remove, and this is what that looks like from the outside: the
        order is the database's, not the caller's.
        """
        created = _post_note(client, symbols=["600519", "sh000858"])
        assert [s["code"] for s in created["symbols"]] == ["000858", "600519"]

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
        # `to_title` rides along on every link. It was absent from the wire format
        # and the interface filled the gap from the list on screen, which is the
        # state the note detail panel rendered a raw id in.
        assert created["links"] == [
            {
                "to_kind": "card",
                "to_id": card_id,
                "to_title": "渠道库存是白酒先行指标",
            }
        ]

    def test_a_note_to_note_link_carries_the_target_title(
        self, client: TestClient
    ) -> None:
        """The case the interface could not serve at all.

        Two notes, one pointing at the other, and the target's title present in the
        source note's own payload. Before this the field did not exist on the wire,
        so a row could only be named when the target happened to be in the list
        currently loaded.
        """
        target = _post_note(client, title="目标笔记的标题")
        source = _post_note(
            client,
            title="源笔记",
            links=[{"to_kind": "note", "to_id": target["id"]}],
        )
        assert source["links"] == [
            {
                "to_kind": "note",
                "to_id": target["id"],
                "to_title": "目标笔记的标题",
            }
        ]


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


class TestBacklinks:
    """`GET /notes/{id}/backlinks` (spec 045 stage C).

    ⭐ This route exists because `notes.backlinks_for` had been in the repository since
    spec 026 **with a test and no caller** — the shape `status.md` carried as
    「反链有函数无面板」. ⭐ So the first test here is not about backlinks at all; it is
    that the route is reachable at all, because FastAPI matches in declaration order
    and this repo has been bitten by that twice.
    """

    def test_the_route_is_not_captured_by_the_note_id_route(
        self, client: TestClient
    ) -> None:
        """`/{note_id}` is a wildcard and `/backlinks` is declared after it.

        ⭐ **This is the same assertion `notes.py` already carries for `/due`, and it is
        written again rather than shared** because the failure is per-route: moving one
        handler fixes one route and breaks nothing about the other, ⭐ and a helper that
        "checked the ordering" would need to know the route table to do it.
        """
        created = _post_note(client)
        response = client.get(f"/api/v1/notes/{created['id']}/backlinks")
        assert response.status_code == 200, response.text

    def test_a_note_with_nothing_pointing_at_it_lists_nothing(
        self, client: TestClient
    ) -> None:
        """⭐ Empty is the honest answer and it is a **200 with `[]`**, not a 404. A
        backlink list is asked about a note that very much exists."""
        created = _post_note(client)
        assert client.get(f"/api/v1/notes/{created['id']}/backlinks").json() == []

    def test_a_note_pointing_at_another_appears_in_its_backlinks(
        self, client: TestClient
    ) -> None:
        """The feature, and the direction that is easy to get backwards.

        ⭐ **A links at B means B's list contains A** — not A's list containing B. The
        repository function takes `(kind, target_id)` and filters on `to_id`, so writing
        the endpoint against the wrong side produces a route that answers 200 with the
        right shape and the wrong notes in it, ⭐ which is the kind of defect no status
        code catches.
        """
        target = _post_note(client, title="目标笔记")
        source = _post_note(client, title="引用它的那条")
        linked = client.post(
            f"/api/v1/notes/{source['id']}/links",
            json={"to_kind": "note", "to_id": target["id"]},
        )
        assert linked.status_code == 200, linked.text

        rows = client.get(f"/api/v1/notes/{target['id']}/backlinks").json()
        assert [(row["from_note_id"], row["title"]) for row in rows] == [
            (source["id"], "引用它的那条")
        ]
        # ⭐ And the reverse direction is empty. One assertion, because "the list is
        # right" and "the other list is right" fail together when the filter is wrong.
        assert client.get(f"/api/v1/notes/{source['id']}/backlinks").json() == []

    def test_the_row_carries_the_id_so_the_list_is_clickable(
        self, client: TestClient
    ) -> None:
        """⭐ A list of titles with no way to open them is a list of labels, and the
        whole point of a backlink is to be followed."""
        target = _post_note(client)
        source = _post_note(client)
        client.post(
            f"/api/v1/notes/{source['id']}/links",
            json={"to_kind": "note", "to_id": target["id"]},
        )
        row = client.get(f"/api/v1/notes/{target['id']}/backlinks").json()[0]
        assert row["from_note_id"] == source["id"]

    def test_the_row_does_not_carry_the_body(self, client: TestClient) -> None:
        """⭐ The endpoint is not a way to fetch any note the caller can name.

        `GET /notes/{id}` already serves a body to anyone with an id, so this is not a
        new capability — but a backlink list is rendered in a side panel beside a
        record, and shipping every linked note's full text there would make the panel
        cost proportional to the vault rather than to the panel.
        """
        target = _post_note(client)
        source = _post_note(client, body="一段只应该出现在 GET 单条里的正文")
        client.post(
            f"/api/v1/notes/{source['id']}/links",
            json={"to_kind": "note", "to_id": target["id"]},
        )
        row = client.get(f"/api/v1/notes/{target['id']}/backlinks").json()[0]
        assert set(row) == {"from_note_id", "title"}
        assert "正文" not in row["title"]

    def test_a_missing_note_is_a_404_and_not_a_400(self, client: TestClient) -> None:
        """⭐ **The status code is the assertion, and it is not obvious.**

        `NOTE_NOT_FOUND` is **not** in `errors.py`'s status table, so an uncaught
        `NoteNotFoundError` falls through to the 400 default. ⭐ `GET /{note_id}` carries
        an explicit `try/except` for exactly this, and this route has to as well — a
        400 for a missing note is a wrong answer about a missing note, on the one route
        where "missing" is a plausible thing for a client to ask.
        """
        response = client.get("/api/v1/notes/note_9999999999999/backlinks")
        assert response.status_code == 404, response.text

    def test_a_backlink_does_not_survive_its_note(self, client: TestClient) -> None:
        """⭐ **This test replaced one that asserted something untrue, and the
        replacement is the interesting part.**

        The first version claimed "nothing cascades a deleted note's outgoing links, so
        the handler skips ids that no longer resolve". ⭐ That was wrong on both halves,
        and it was wrong because it was written from an assumption: the mutation check
        showed that removing the handler's `if row is not None` left the suite green, ⭐
        and the probe answered why — `note_links` **does** cascade, and `get_by_id`
        **raises** rather than returning `None`, so the guard was unreachable.

        ⭐ So the guard was deleted (see the handler) and this test now pins the
        behaviour that is actually true: deleting the linking note deletes the link, and
        the list is empty afterwards without any filtering. ⭐ The route therefore has
        nothing to defend against, and saying so in a test is worth more than a guard
        that looks like it is defending something.
        """
        from alphacouncil.core.config import get_settings
        from alphacouncil.storage import db as sdb

        target = _post_note(client)
        source = _post_note(client)
        client.post(
            f"/api/v1/notes/{source['id']}/links",
            json={"to_kind": "note", "to_id": target["id"]},
        )
        assert len(client.get(f"/api/v1/notes/{target['id']}/backlinks").json()) == 1

        connection = sdb.connect(get_settings().database_path)
        try:
            with connection:
                connection.execute("DELETE FROM notes WHERE id = ?", (source["id"],))
            # ⭐ **The setup asserts itself.** The first version did not, which is why it
            # stayed green after the behaviour it was testing was removed. ⭐ A test that
            # cannot fail because its own preparation quietly did nothing is a test that
            # asserts nothing, and it looks exactly like a test that passed.
            remaining = connection.execute(
                "SELECT COUNT(*) FROM note_links WHERE from_note_id = ?", (source["id"],)
            ).fetchone()[0]
        finally:
            connection.close()
        assert remaining == 0, "the link row outlived its note — the cascade is not there"

        assert client.get(f"/api/v1/notes/{target['id']}/backlinks").json() == []


class TestUnlinking:
    """`DELETE /notes/{id}/links/{kind}/{target}` (spec 045 · 知识库基本功能).

    ⭐ **This endpoint exists because the link was a one-way door.** A note could be
    pointed at another note, a card or a decision, and never un-pointed — ⭐ so a
    claim the reader has stopped making stayed in the graph forever, ⭐ and in a
    knowledge base 「我不再认为 A 和 B 有关」 is a statement the reader has to be able
    to make. ⭐ `note_tags` has had `POST` + `DELETE` since spec 026 ⭐ and
    `note_links` never had either, ⭐ which is a gap rather than a design.
    """

    def test_a_link_can_be_taken_back(self, client: TestClient) -> None:
        source = _post_note(client, title="说 A 和 B 有关的那条")
        target = _post_note(client, title="B")
        client.post(
            f"/api/v1/notes/{source['id']}/links",
            json={"to_kind": "note", "to_id": target["id"]},
        )

        response = client.delete(
            f"/api/v1/notes/{source['id']}/links/note/{target['id']}"
        )
        assert response.status_code == 200, response.text
        # ⭐ **The whole note comes back, and the link is gone from it.** ⭐ Asserting
        # on the response rather than on a follow-up GET is what pins the contract's
        # shape: the tag routes return `_to_read(...)` too, ⭐ and a reader of this
        # test should not have to fetch a second time to find out.
        assert response.json()["links"] == []
        assert client.get(f"/api/v1/notes/{target['id']}/backlinks").json() == []

    def test_removing_one_link_leaves_the_others(self, client: TestClient) -> None:
        """⭐ **The one that needs a test to exist.**

        `note_links` is keyed on `(from_note_id, to_kind, to_id)`, ⭐ and a delete
        written on two columns — the shape `note_tags` uses, ⭐ where the tag is the
        only variable — **removes every link to that id regardless of kind**. ⭐
        `card_7` and `decision_7` are different things, ⭐ and a note may well name
        both, ⭐ so the difference between a two-column and a three-column delete is
        invisible until a reader has both.
        """
        from alphacouncil.core.config import get_settings
        from alphacouncil.storage import db as sdb

        source = _post_note(client)
        first = _post_note(client, title="第一个")
        second = _post_note(client, title="第二个")
        for target in (first, second):
            client.post(
                f"/api/v1/notes/{source['id']}/links",
                json={"to_kind": "note", "to_id": target["id"]},
            )
        # ⭐ And a *different kind* pointing at the same id text, ⭐ which is the
        # shape a two-column delete cannot tell apart.
        connection = sdb.connect(get_settings().database_path)
        try:
            with connection:
                connection.execute(
                    "INSERT INTO note_links (from_note_id, to_kind, to_id, created_at)"
                    " VALUES (?, 'decision', ?, '2026-01-01T00:00:00.000Z')",
                    (source["id"], first["id"]),
                )
        finally:
            connection.close()

        before = client.get(f"/api/v1/notes/{source['id']}").json()["links"]
        assert len(before) == 3, before

        client.delete(f"/api/v1/notes/{source['id']}/links/note/{first['id']}")
        after = client.get(f"/api/v1/notes/{source['id']}").json()["links"]
        # ⭐ As `(kind, id)` pairs, ⭐ because the kind is part of the identity ⭐ and
        # the first version of this assertion compared a two-element `set` against a
        # `set` of `tuple`s, ⭐ which is false for every input ⭐ and read as a
        # product bug. ⭐ **Assert on the shape the identity actually has.**
        remaining = {(link["to_kind"], link["to_id"]) for link in after}
        assert ("note", first["id"]) not in remaining
        assert ("note", second["id"]) in remaining
        # ⭐ And the same id under a different kind survived, ⭐ which is the whole
        # point of the three-column delete.
        assert ("decision", first["id"]) in remaining
        assert len(after) == 2, after

    def test_removing_a_link_that_is_not_there_succeeds(self, client: TestClient) -> None:
        """⭐ **Idempotence, stated because the alternative was tempting.**

        The caller's intent — 「this note does not point there」 ⭐ — is satisfied
        whether or not it ever did, ⭐ and answering 404 would make an idempotent
        action look like a failure. ⭐ A future reader adding 「for consistency with
        the other routes」 ⭐ would break a retry, ⭐ so the behaviour is pinned.
        """
        source = _post_note(client)
        target = _post_note(client)
        response = client.delete(
            f"/api/v1/notes/{source['id']}/links/note/{target['id']}"
        )
        assert response.status_code == 200, response.text

    def test_a_missing_note_is_a_404(self, client: TestClient) -> None:
        """⭐ The same trap the backlinks route carries, ⭐ and the reason the handler
        is not a bare delete: the note has to exist, ⭐ because a link from a note
        that is gone is not a thing to store."""
        response = client.delete(
            "/api/v1/notes/note_9999999999999/links/note/note_1"
        )
        assert response.status_code == 404, response.text

    def test_an_unknown_kind_is_rejected(self, client: TestClient) -> None:
        """⭐ `LinkKind(...)` raises on a string that is not a kind, ⭐ and the answer
        is a 500 unless something catches it. ⭐ Asserting it is a 4xx says the route
        treats a malformed path as a client error ⭐ rather than as a bug."""
        source = _post_note(client)
        response = client.delete(
            f"/api/v1/notes/{source['id']}/links/planet/{source['id']}"
        )
        assert 400 <= response.status_code < 500, response.text
