"""Forwarding import — **the implementation lives in :mod:`alphacouncil.core.console`**.

## ⭐ Why this file still exists

``scripts/dev.py`` and its sibling tools are run as **scripts**, so they import this by
the bare name ``_console`` with ``scripts/`` on ``sys.path``. ⭐ That is convenient and it
worked, until spec 044 needed the same helper from **inside the package** —
``alphacouncil/notify/__main__.py`` is a product command run as ``python -m
alphacouncil.notify``, ⭐ where ``scripts/`` is **not** on the path, ⭐ and the import failed
with ``ModuleNotFoundError: No module named '_console'``.

⭐ Two homes were the alternatives and both are worse:

* **copy** the helper into the package — ⭐ then two copies drift, and the drift would show
  up as 「门禁在一种终端上画得出 ✓ 而通知命令在另一种上画不出」, which is `regressions/0004`
  wearing a different hat.
* **inline three lines** of ``reconfigure`` in ``__main__`` — ⭐ and then ``S-13``
  (``tool-encoding``) would flag the product command for not calling ``use_utf8()``,
  ⭐ because the rule is 「call the helper」 and the helper would not be the one it looks for.

So the implementation moved **into the package**, where both callers can reach it, and this
module is the path the scripts keep using. ⭐ One home, two importers — which is the whole
rule of ``一个概念一个家`` applied to a file rather than to a name.

⭐ One phrasing note, because it is why the sentences above avoid the full-width comma.
⭐ **I got this wrong the first time and wrote the wrong explanation into this file.** I
had documented that ``RUF002`` reads docstrings only, and that the Chinese prose in ``#``
comments is therefore never flagged. ⭐ The gate says otherwise: ``RUF002`` covers
docstrings and ``RUF003`` covers **comments**, and it flagged one of each on the first run
after that note was written. ⭐ The comfortable half-truth was 「docstrings but not
comments」 and the true rule is 「both, in Python files, unlike the Markdown under
``.ai/``」.

⭐ So the note was deleted and rewritten rather than reworded. ⭐ A comment that explains
why a lint rule is escaped, written from a half-remembering of the rule, is worse than no
comment: it is the kind of thing a reader trusts instead of checking, and these two claims
were written in the confident voice this repository reserves for things that have been
measured. ⭐ Write 「I checked」 or write nothing.
"""

from __future__ import annotations

from alphacouncil.core.console import use_utf8

__all__ = ["use_utf8"]
