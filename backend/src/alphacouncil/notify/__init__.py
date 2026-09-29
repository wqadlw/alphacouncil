"""Outbound notification channels.

**Transport only.** Every module here takes a rendered subject/body and delivers it.
⭐ Nothing in this package decides *what* deserves sending — that belongs to the
scheduler, and a channel that also made the decision would be two things in one place.

**Failure is a return value.** A refused server must not take down whatever decided to
send. Each ``send_*`` returns ``bool`` and logs at ``warning``, so a dropped notification
is visible rather than merely absent.

Reuse notes, from absorbing TSP (`references/research/2026-09-29-tsp-capability-matrix.md`):

* `email` — copied from `tick-stock-panel` v0.2.2 (MIT), attribution kept in its docstring.
* Webhook channels (Feishu signature / WeCom markdown / generic JSON + HMAC-SHA256) are
  **not copied yet**. S-01 (`no-raw-http`) rejects `import httpx` outside `providers/`,
  and its prescribed fix — route through the provider layer — is wrong for a webhook POST,
  because that layer is the *market data* router. The HTTP egress boundary has to be
  decided first; see spec 033 §2. ⭐ A notification channel is not a reason to weaken a
  red-line rule, and it is not a reason to smuggle in a second HTTP client either.
"""

from alphacouncil.notify.email import is_configured, is_valid_email, send_email

__all__ = ["is_configured", "is_valid_email", "send_email"]
