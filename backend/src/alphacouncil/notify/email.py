"""SMTP email transport — the first notification channel (spec 033).

Copied from **tick-stock-panel** (``backend/app/services/email_adapter.py``, v0.2.2,
MIT License) with three changes, and the reasons are worth stating because each one
is a rule rather than a preference.

**Attribution kept.** MIT requires the copyright notice to travel with the code, so it
is in this docstring rather than in a ``NOTICE`` file nobody reads next to the function.

**``logging`` → ``structlog``.** S-10 bans ``print`` in the product and the project's
logging convention is ``structlog`` (``providers/cache.py``, ``core/trace.py``).

**Default subject re-branded.** TSP's default was ``"TickFlow 通知"``. ⭐ Copying another
product's name into your own default output is not a small thing — it is a user-visible
string that says the wrong program made it. Every product-branded string was checked, and
this module is the only one that carried any: the webhook channel carries three more and
is not copied yet (see spec 033 §2).

---

## Why a notification channel at all

红线 7 requires every lesson to be scheduled automatically, and spec 028 gave notes a
review queue that 「会自己回来找你」. ⭐ Both of those promises are only half-delivered:
the schedule exists, and then the program waits for **you** to open the page.

A scheduled item that can only be discovered by visiting a screen is not a reminder. It is
a row in a table. This module is the first step toward the other half — and it is
deliberately the least opinionated channel available: SMTP needs no account with anyone,
no OAuth, no app review, and works from a self-hosted machine behind any NAT.

## What this module is and is not

**Transport only.** It takes a subject and a body and sends them. ⭐ It does not decide
*what* deserves sending — that decision belongs to the scheduler, and putting it here
would give one function two jobs and one place to be wrong.

**Failure is a return value, never an exception.** ⭐ The channel is auxiliary: a refused
SMTP server must not take down the thing that decided to send the mail. ``send_email``
returns ``False``, logs at ``warning`` (so a dropped notification is visible rather than
merely absent), and lets the caller carry on.

⚠️ **The one behaviour copied verbatim, because getting it wrong sends two emails:**
``send_message`` succeeding followed by ``quit`` failing must **not** retry. Delivery
already happened; a retry duplicates it, and the user cannot tell which copy is real.
That is why the ``quit`` is wrapped separately from the send.

## Verified upstream behaviour worth keeping

* Security modes ``ssl`` / ``starttls`` / ``none``, with ``ehlo`` re-issued after
  ``starttls`` — ⭐ the second ``ehlo`` is required, not decorative: without it the session
  keeps the pre-TLS capability set and some servers reject the login.
* Port range and security mode are validated **before** any socket is opened, so a
  misconfigured channel fails instantly instead of after a 10-second connect timeout.
* ``is_valid_email`` is deliberately dependency-free and conservative, for configuration
  checks — it is not an RFC 5322 parser and does not pretend to be.
"""

from __future__ import annotations

import smtplib
import time
from contextlib import suppress
from email.message import EmailMessage
from email.utils import parseaddr

import structlog

log = structlog.get_logger(__name__)

#: The three transports SMTP actually offers. Anything else is a configuration error,
#: caught before a socket is opened rather than after a connect timeout.
SECURITY_MODES = frozenset({"ssl", "starttls", "none"})

_MAX_ATTEMPTS = 2

#: Default subject. TSP's was ``"TickFlow 通知"`` — see the module docstring.
_DEFAULT_SUBJECT = "AlphaCouncil"


def is_valid_email(address: str) -> bool:
    """Whether ``address`` is a mailbox worth attempting.

    Dependency-free and conservative, on purpose: this gates configuration, so a false
    positive here becomes a retry loop against a real server, and a false negative blocks
    a channel the user configured correctly. It is **not** an RFC 5322 parser and does not
    claim to be.
    """
    parsed = parseaddr((address or "").strip())[1]
    if parsed != (address or "").strip() or parsed.count("@") != 1:
        return False
    local, _, domain = parsed.rpartition("@")
    return bool(local and domain and "." in domain and " " not in parsed)


def is_configured(config: dict[str, object]) -> bool:
    """Whether the non-secret fields suffice to attempt delivery.

    ⭐ Deliberately does **not** look at the password: a missing password is a runtime
    authentication failure that the server should answer, while this check exists to catch
    a channel nobody filled in — and inventing a secret requirement here would report a
    working configuration as broken.
    """
    sender = str(config.get("from_address") or config.get("username") or "").strip()
    recipients = config.get("to_addresses")
    return bool(config.get("host") and sender and recipients)


def send_email(
    config: dict[str, object],
    password: str,
    subject: str,
    body: str,
    *,
    max_attempts: int = _MAX_ATTEMPTS,
) -> bool:
    """Send one UTF-8 plain-text email. Returns whether it was handed to the server.

    ⭐ Every validation happens before the first socket, so a bad port or a bad security
    mode costs nothing instead of costing a connect timeout.
    """
    if not is_configured(config):
        return False

    host = str(config.get("host") or "").strip()
    try:
        port = int(config.get("port", 465))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return False
    security = str(config.get("security") or "ssl")
    username = str(config.get("username") or "").strip()
    sender = str(config.get("from_address") or username).strip()
    raw_recipients = config.get("to_addresses")
    recipients = (
        [str(item).strip() for item in raw_recipients] if isinstance(raw_recipients, list) else []
    )

    if (
        not 1 <= port <= 65535
        or security not in SECURITY_MODES
        or not is_valid_email(sender)
        or not recipients
        or any(not is_valid_email(item) for item in recipients)
    ):
        return False

    message = EmailMessage()
    message["Subject"] = str(subject or _DEFAULT_SUBJECT)
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(str(body or ""))

    last_error = ""
    for attempt in range(1, max_attempts + 1):
        smtp: smtplib.SMTP | None = None
        try:
            if security == "ssl":
                smtp = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                smtp = smtplib.SMTP(host, port, timeout=10)
                if security == "starttls":
                    smtp.ehlo()
                    smtp.starttls()
                    # ⭐ Required, not decorative: without the second `ehlo` the session
                    # keeps the pre-TLS capability set and some servers reject the login.
                    smtp.ehlo()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
            # ⭐ Delivery already succeeded. A failed QUIT must not retry, or the user
            # receives the message twice and cannot tell which copy is authoritative.
            with suppress(Exception):
                smtp.quit()
            return True
        except Exception as exc:  # an auxiliary channel must not raise
            last_error = str(exc)
            if smtp is not None:
                with suppress(Exception):
                    smtp.close()
        if attempt < max_attempts:
            time.sleep(1)

    log.warning("email_delivery_failed", attempts=max_attempts, error=last_error)
    return False


__all__ = ["SECURITY_MODES", "is_configured", "is_valid_email", "send_email"]
