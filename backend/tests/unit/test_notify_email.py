"""Tests for the SMTP channel (spec 033).

## What is actually asserted, and why not more

No test opens a socket. ``smtplib.SMTP`` is replaced with a recording double, and the
tests assert on **what would have been sent** — host, port, security handshake order,
login, recipients, and above all *whether a second attempt happens*.

⭐ The retry behaviour is the part worth pinning. Two rules exist and they pull in opposite
directions:

* a send that raises may be retried (transient network failure);
* ⭐ a send that **succeeded** followed by a failing ``quit`` may **not** be retried, or the
  user receives the message twice.

The second is invisible to the first. A test that only checks "it retries on failure"
passes while the duplicate-email bug is present, ⭐ because the two paths return from
different places. So there is a dedicated test for it.

The other test that earns its place: validation happens **before** any socket, because a
bad port should not cost a 10-second connect timeout on every send.
"""

from __future__ import annotations

import smtplib
from typing import Any, ClassVar

import pytest

from alphacouncil.notify.email import (
    SECURITY_MODES,
    is_configured,
    is_valid_email,
    send_email,
)


class FakeSMTP:
    """A recording ``smtplib`` double.

    ``quit`` failing is a first-class knob rather than an exception to be raised, because
    the duplicate-email bug only appears when the send succeeds and the goodbye fails —
    which is exactly the combination a normal failure test never produces.
    """

    instances: ClassVar[list[FakeSMTP]] = []

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        *,
        fail_send: bool = False,
        fail_quit: bool = False,
        fail_login: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.fail_send = fail_send
        self.fail_quit = fail_quit
        self.fail_login = fail_login
        self.calls: list[str] = []
        self.sent: list[Any] = []
        self.closed = False
        FakeSMTP.instances.append(self)

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, username: str, password: str) -> None:
        self.calls.append(f"login:{username}")
        if self.fail_login:
            raise smtplib.SMTPAuthenticationError(535, "bad credentials")

    def send_message(self, message: Any) -> None:
        self.calls.append("send")
        if self.fail_send:
            raise smtplib.SMTPException("connection reset")
        self.sent.append(message)

    def quit(self) -> None:
        self.calls.append("quit")
        if self.fail_quit:
            raise smtplib.SMTPException("server closed the connection")

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset() -> None:
    FakeSMTP.instances = []


def _config(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "host": "smtp.example.com",
        "port": 465,
        "security": "ssl",
        "username": "me@example.com",
        "password": "unused",
        "from_address": "me@example.com",
        "to_addresses": ["you@example.com"],
    }
    base.update(overrides)
    return base


class TestIsValidEmail:
    @pytest.mark.parametrize(
        "address", ["me@example.com", "first.last@sub.example.co.uk"]
    )
    def test_accepts_ordinary_mailboxes(self, address: str) -> None:
        assert is_valid_email(address) is True

    @pytest.mark.parametrize(
        "address",
        [
            "",
            "   ",
            "not-an-address",
            "@example.com",
            "me@",
            "me@example",
            "me@@example.com",
            "Name <me@example.com>",  # parseaddr strips the name, so it is not the input
            "me @example.com",
        ],
    )
    def test_rejects(self, address: str) -> None:
        assert is_valid_email(address) is False

    def test_a_none_recipient_list_is_not_ready(self) -> None:
        """⭐ ``dict.get()`` returns ``None``, so this is a real input, not a hypothetical.

        It was previously a stray ``None`` in the parametrised list above, which made that
        list look more thorough than the function's contract — and cost a ``type: ignore``
        mypy reported as unused, because the declared parameter is ``str``. ⭐ The honest
        version asserts it through the caller that can actually produce it.
        """
        assert is_configured(_config(to_addresses=None)) is False

    def test_a_none_sender_is_still_ready_when_username_can_stand_in(self) -> None:
        """⭐ The fallback is the point, and this is what it looks like from outside.

        The first version of this test expected ``from_address=None`` to mean
        「unconfigured」 and failed — ⭐ because falling back to ``username`` is exactly the
        behaviour ``test_username_can_stand_in_for_from_address`` asserts. A test that
        contradicts another test of the same function is not testing the function.
        """
        assert is_configured(_config(from_address=None)) is True

    def test_a_none_sender_with_no_username_is_not_ready(self) -> None:
        """Both sources of a sender gone, so there is nothing to send as."""
        assert is_configured(_config(from_address=None, username="")) is False


class TestIsConfigured:
    def test_a_complete_channel_is_ready(self) -> None:
        assert is_configured(_config()) is True

    @pytest.mark.parametrize("missing", ["host", "to_addresses"])
    def test_a_missing_field_is_not_ready(self, missing: str) -> None:
        """⭐ ``from_address`` is deliberately **not** in this list.

        It fell out of an earlier version of this test that expected removing it to mean
        "unconfigured" — while ``is_configured`` falls back to ``username`` as the sender
        and a separate test asserts that fallback. ⭐ The parametrisation was asserting a
        behaviour the module was written to avoid.
        """
        config = _config()
        config.pop(missing)
        assert is_configured(config) is False

    def test_username_can_stand_in_for_from_address(self) -> None:
        config = _config()
        config.pop("from_address")
        assert is_configured(config) is True

    def test_the_password_is_never_part_of_this_check(self) -> None:
        """⭐ A missing secret is the server's answer to give, not this function's.

        Inventing a password requirement here would report a working channel as broken,
        and the fix a user would try — typing a password they already set — changes nothing.
        """
        assert is_configured(_config(password="")) is True


class TestValidationHappensBeforeAnySocket:
    @pytest.mark.parametrize(
        ("overrides", "why"),
        [
            ({"port": 0}, "port below range"),
            ({"port": 70000}, "port above range"),
            ({"port": "not-a-number"}, "unparseable port"),
            ({"security": "tls"}, "unknown security mode"),
            ({"to_addresses": []}, "no recipients"),
            ({"to_addresses": ["bad-address"]}, "invalid recipient"),
            ({"from_address": "bad-address"}, "invalid sender"),
        ],
    )
    def test_a_bad_configuration_never_opens_a_connection(
        self, monkeypatch: pytest.MonkeyPatch, overrides: dict[str, Any], why: str
    ) -> None:
        """⭐ A typo in the port must cost nothing, not a 10-second connect timeout."""

        def explode(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError(f"a socket was opened for: {why}")

        monkeypatch.setattr(smtplib, "SMTP_SSL", explode)
        monkeypatch.setattr(smtplib, "SMTP", explode)
        assert send_email(_config(**overrides), "pw", "s", "b") is False


class TestDelivery:
    def test_ssl_is_the_default_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
        assert send_email(_config(), "pw", "该复习了", "正文") is True
        client = FakeSMTP.instances[0]
        assert (client.host, client.port) == ("smtp.example.com", 465)
        # ⭐ Only the transport-relevant order. An earlier version asserted the whole call
        # list, which meant it was also asserting that authentication never happens —
        # an accident of the double having a username filled in.
        assert client.calls.index("send") < client.calls.index("quit")

    def test_starttls_re_issues_ehlo_after_upgrading(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ Without the second ``ehlo`` the session keeps the pre-TLS capability set."""
        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        config = _config(port=587, security="starttls")
        assert send_email(config, "pw", "s", "b") is True
        assert FakeSMTP.instances[0].calls[:3] == ["ehlo", "starttls", "ehlo"]

    def test_plain_smtp_does_not_negotiate_tls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        assert send_email(_config(port=25, security="none"), "pw", "s", "b") is True
        assert "starttls" not in FakeSMTP.instances[0].calls

    def test_the_message_is_utf8_plain_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
        assert send_email(_config(), "pw", "该复习了", "贵州茅台 批价跟踪") is True
        message = FakeSMTP.instances[0].sent[0]
        assert message["To"] == "you@example.com"
        assert isinstance(message.get_content(), str)
        # ⭐ A CJK subject survives as an actual header, not mojibake.
        assert message["Subject"] == "该复习了"
        assert "贵州茅台" in message.get_content()

    def test_an_untitled_message_still_carries_our_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ Not TSP's product name. A default subject is user-visible text."""
        monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
        assert send_email(_config(), "pw", "", "b") is True
        assert FakeSMTP.instances[0].sent[0]["Subject"] == "AlphaCouncil"

    def test_no_username_means_no_login(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
        config = _config(username="", from_address="robot@example.com")
        assert send_email(config, "", "s", "b") is True
        assert not any(call.startswith("login") for call in FakeSMTP.instances[0].calls)


class TestRetrySemantics:
    def test_a_failed_send_is_retried_and_the_second_one_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ Retry and repetition are different, and the double has to tell them apart.

        The first version failed *every* attempt whenever ``fail_send`` was set, so the
        test was really asserting "two connections were made" — which a retry loop that
        never succeeds also satisfies. ⭐ Failing only the first attempt is what makes this
        test about the retry instead of about the counter.
        """
        monkeypatch.setattr("time.sleep", lambda _seconds: None)
        attempts = 0

        def flaky(*args: Any, **kwargs: Any) -> FakeSMTP:
            nonlocal attempts
            attempts += 1
            return FakeSMTP(*args, **kwargs, fail_send=attempts == 1)

        monkeypatch.setattr(smtplib, "SMTP_SSL", flaky)
        assert send_email(_config(), "pw", "s", "b", max_attempts=2) is True
        assert len(FakeSMTP.instances) == 2
        assert FakeSMTP.instances[0].calls == ["login:me@example.com", "send"]
        # ⭐ The failed connection is closed, so a retry does not leak a socket.
        assert FakeSMTP.instances[0].closed is True
        assert FakeSMTP.instances[1].sent, "the second attempt delivered nothing"

    def test_a_failed_quit_is_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """⭐ The duplicate-email bug, named as a test.

        ``send_message`` succeeded, so the message is already delivered. Retrying because
        ``quit`` raised sends it a second time, and the user has no way to tell which copy
        is authoritative. ⭐ The other retry test passes while this bug is present, because
        the two paths return from different places.
        """

        def with_failing_quit(*args: Any, **kwargs: Any) -> FakeSMTP:
            return FakeSMTP(*args, **kwargs, fail_quit=True)

        monkeypatch.setattr(smtplib, "SMTP_SSL", with_failing_quit)
        assert send_email(_config(), "pw", "s", "b", max_attempts=3) is True
        assert len(FakeSMTP.instances) == 1, "the message was delivered twice"

    def test_an_authentication_failure_is_reported_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
        monkeypatch.setattr("time.sleep", lambda _seconds: None)
        config = _config()

        def refusing(*args: Any, **kwargs: Any) -> FakeSMTP:
            return FakeSMTP(*args, **kwargs, fail_login=True)

        monkeypatch.setattr(smtplib, "SMTP_SSL", refusing)
        # ⭐ An auxiliary channel must not raise into the scheduler that called it.
        assert send_email(config, "wrong", "s", "b", max_attempts=1) is False

    def test_every_mode_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        for mode in sorted(SECURITY_MODES):
            assert send_email(_config(security=mode), "pw", "s", "b") is True
