"""Searching notes over HTTP (spec 027).

The repository tests already know FTS5 works. These are about the **wire**:
that the parameter reaches the right path, that a two-character query survives
the round trip (a URL-encoding or `min_length` slip would make the whole feature
silently useless for the most natural query in the domain), and that `q` and
`tag` compose rather than one quietly winning.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def _write(client: TestClient, title: str, body: str = "正文", **extra: Any) -> str:
    payload: dict[str, Any] = {"title": title, "body": body}
    payload.update(extra)
    response = client.post("/api/v1/notes", json=payload)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _titles(client: TestClient, **params: str) -> list[str]:
    """The titles `GET /api/v1/notes` returns for these query parameters."""
    response = client.get("/api/v1/notes", params=params)
    assert response.status_code == 200, response.text
    return [str(note["title"]) for note in response.json()]


class TestSearchOverHttp:
    def test_a_two_character_query_survives_the_round_trip(
        self, client: TestClient
    ) -> None:
        """⭐ The whole reason `search` has a second path.

        If a `min_length` on the query parameter, or a URL-encoding slip, dropped
        two-character queries, the feature would work in the repository tests and
        return nothing in the app — and the tests would still be green.
        """
        _write(client, "利率上行的观察")
        _write(client, "白酒行业产能出清")
        assert _titles(client, q="利率") == ["利率上行的观察"]

    def test_a_longer_query_finds_text_in_the_body(self, client: TestClient) -> None:
        _write(client, "标题无关", body="先看自由现金流，再看增长。")
        assert _titles(client, q="自由现金流") == ["标题无关"]

    def test_no_parameters_returns_everything(self, client: TestClient) -> None:
        _write(client, "一")
        _write(client, "二")
        assert len(client.get("/api/v1/notes").json()) == 2

    def test_an_empty_query_is_not_a_search(self, client: TestClient) -> None:
        """Clearing the box must not empty the page — that is the most common
        single keystroke in a search field."""
        _write(client, "一")
        _write(client, "二")
        assert len(client.get("/api/v1/notes", params={"q": ""}).json()) == 2
        assert len(client.get("/api/v1/notes", params={"q": "   "}).json()) == 2

    def test_a_query_matching_nothing_returns_an_empty_list(
        self, client: TestClient
    ) -> None:
        """Empty, not a 404. 「没有找到」 and 「这条笔记不存在」 are different
        answers and only one of them is a bug."""
        _write(client, "利率上行的观察")
        response = client.get("/api/v1/notes", params={"q": "一个不存在的长查询"})
        assert response.status_code == 200
        assert response.json() == []

    def test_query_syntax_is_searched_not_executed(self, client: TestClient) -> None:
        """A `"` or `NEAR` in the box must not become an error response.

        This is the failure a reader would report as 「搜索框坏了」 rather than as
        「我的查询写法不对」 — and the honest answer is the second one, so the API
        has to deliver it as text.
        """
        _write(client, '标题里有"引号"标记')
        response = client.get("/api/v1/notes", params={"q": '"引号"标记'})
        assert response.status_code == 200
        assert [n["title"] for n in response.json()] == ['标题里有"引号"标记']

    def test_a_percent_sign_does_not_return_the_whole_vault(
        self, client: TestClient
    ) -> None:
        _write(client, "标题里有%符号")
        _write(client, "普通一")
        _write(client, "普通二")
        response = client.get("/api/v1/notes", params={"q": "%"})
        assert response.status_code == 200
        assert [n["title"] for n in response.json()] == ["标题里有%符号"]


class TestSearchComposesWithTheTagFilter:
    def test_a_tag_alone_still_filters(self, client: TestClient) -> None:
        _write(client, "宏观判断", tags=["宏观"])
        _write(client, "估值判断", tags=["估值"])
        assert _titles(client, tag="宏观") == ["宏观判断"]

    def test_the_tag_filter_alone_is_not_narrowed_by_an_absent_query(
        self, client: TestClient
    ) -> None:
        """`?tag=宏观` with no `q` must be the whole tag, not an accidental match.

        Worth a test of its own because the composition logic reads
        ``if tag and q and q.strip()`` — three conditions, and it would be easy to
        leave one of them making the filter a no-op.
        """
        _write(client, "一", body="正文甲", tags=["宏观"])
        _write(client, "二", body="正文乙", tags=["宏观"])
        _write(client, "三", body="正文丙", tags=["估值"])
        assert len(_titles(client, tag="宏观")) == 2

    def test_a_query_and_a_tag_narrow_together(self, client: TestClient) -> None:
        """⭐ The fixture must make the two filters **distinguishable**.

        The first draft had two notes: one with the text and the tag, one with
        neither. That cannot tell 「search then filter by tag」 apart from 「filter
        by tag and ignore the query」 — both return the first note, so the test
        passed with the query dropped entirely. A mutation check caught it.

        The fix is a note that **carries the tag but not the text**. Now the tag
        alone returns two notes and the combination returns one, so ignoring the
        query is a visible difference.

        ⭐ Compared as sets, not sequences. These notes are created in the same
        millisecond, and the list orders by ``updated_at DESC, id DESC`` — so the
        *later*-created note sorts first. The first draft asserted creation order
        and failed on correct behaviour; order is pinned deliberately in
        ``test_notes_search.py`` and is not what these two tests are about.
        """
        _write(client, "宏观判断", body="流动性收紧", tags=["宏观"])
        _write(client, "宏观但正文无关", body="完全另一件事", tags=["宏观"])
        _write(client, "估值判断", body="流动性宽松", tags=["估值"])

        # The tag alone is deliberately wider than the answer below.
        assert set(_titles(client, tag="宏观")) == {"宏观判断", "宏观但正文无关"}
        assert _titles(client, q="流动性", tag="宏观") == ["宏观判断"]

    def test_a_query_narrows_a_tag_that_matches_several_notes(
        self, client: TestClient
    ) -> None:
        """The same property from the other side: one text, two tags."""
        _write(client, "一", body="共同正文", tags=["宏观", "估值"])
        _write(client, "二", body="共同正文", tags=["宏观"])
        _write(client, "三", body="别的正文", tags=["宏观"])

        assert set(_titles(client, q="共同正文", tag="宏观")) == {"一", "二"}

    def test_the_tag_filter_is_still_exact_when_combined(
        self, client: TestClient
    ) -> None:
        """The prefix bug must not reappear on the combined path.

        Two notes share a body so both survive the search, and the tags are
        `宏观` and `宏观债` — the exact pair that `LIKE '%宏观%'` conflates.
        """
        _write(client, "一", body="共同正文", tags=["宏观"])
        _write(client, "二", body="共同正文", tags=["宏观债"])
        assert _titles(client, q="共同正文", tag="宏观") == ["一"]

    def test_an_empty_query_falls_back_to_the_tag_filter(
        self, client: TestClient
    ) -> None:
        """`?q=&tag=宏观` is what a UI sends when the box is cleared but a tag is
        still selected. It must not return the whole vault — that would look like
        the tag filter silently broke."""
        _write(client, "宏观判断", tags=["宏观"])
        _write(client, "估值判断", tags=["估值"])
        assert _titles(client, q="", tag="宏观") == ["宏观判断"]
