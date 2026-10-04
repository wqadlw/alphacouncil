"""Data checks: the ones that read the reader's own rows.

⭐ `constitution.md:841` says the two kinds cannot substitute for each other ⭐ —
⭐ 「『某段代码不该存在』这类缺陷，测试永远抓不住」⭐ — and the converse holds here:
⭐ a data invariant is invisible until the data exists. ⭐ `dangling_target` and
# `counter_evidence_blank` guard the same red lines `S-08` and `S-04` guard on the source
side, ⭐ and **neither can see the other's layer.**

⚠️ Every rule here opens the configured database **read-only** ⭐ — ⭐ see
# ``checks/data.py`` for why the first batch must not be able to write, ⭐ even if a later edit
# to a rule's SQL intends it.
"""
