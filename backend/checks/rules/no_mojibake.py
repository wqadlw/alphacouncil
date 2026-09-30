"""S-15 - a source file whose text is not the text that was written.

**Defect guarded:** the first one this rule found, which is the reason it
exists. ``frontend/src/components/knowledge/BacklinkList.tsx`` shipped in
``4f0cc67`` with three U+FFFD inside its own header comment: the sentence read

    Every other element in the vault answers  这是什␦␦␦;

where it should have read 「这是什么」. One character of Chinese prose had been
replaced by three replacement characters on the way to disk, and nothing in the
gate could see it: it compiles, it renders, the test suite is green, and the
component works. Only the sentence is gone.

Why a gate rather than a habit. "Scan for U+FFFD after writing" is already this
repository's practice, and it has been stated in three failure modes (``F-141``,
``F-144``, and the note in ``F-175`` about a guard that became a veto). A habit
is exactly the thing that fails once, silently, and nobody notices for two
commits. The habit that produced this defect was followed; the write path still
mangled the bytes.

**Two findings, not one, and the split is the point.** The two ways text goes
wrong have different causes and different repairs, so they are different codes:

``CHECK_SOURCE_NOT_UTF8``
    The bytes on disk are not valid UTF-8. The file was written in GBK, latin-1
    or UTF-16, or truncated. Fix: re-save the file as UTF-8.

``CHECK_MOJIBAKE_REPLACEMENT_CHAR``
    The bytes **are** valid UTF-8 and the decoded text **contains** U+FFFD.
    Nothing is undecodable; a replacement character was written into the file
    deliberately, by a tool that had already lost the original. This is the case
    above, and it is the one that is invisible to every other tool in the gate.

**The rule reads bytes, and it must.** ``ScanContext.text()`` decodes with
``errors="replace"`` ⭐ - which is the right default for a rule that wants to
report a syntax error rather than raise, and **exactly wrong for this one**:
decoding with ``errors="replace"`` *manufactures* the character this rule hunts.
A version of this rule written against ``ctx.text()`` would have reported every
file whose bytes are undecodable (correct, accidentally) and would have had no
way at all to see a literal U+FFFD (wrong, and silently). The two codes are the
reason the difference is visible instead of being an accident.

**Text-level, and the exception is deliberate.** ``.ai/checks/README.md`` §4
rule 1 says "AST, never regex" ⭐ - ⭐ and the reason for that rule is that a
regex cannot tell code from a comment. This rule asks a **third** question: is
this byte sequence decodable, and does it contain a character that means
"decoding failed". There is no parse tree for that, and a parse tree is not what
would answer it. A file full of valid Chinese parses fine and is still wrong.

**Exemptions.** ``# noqa: S-15`` is accepted, because a fixture that
*deliberately* contains a replacement character is a legitimate thing to have.
The runner's unreasoned-exemption finding (``CHECK_EXEMPTION_UNREASONED``) still
applies, so the exemption has to say why.

⭐ **And the one fixture that needs it does not use it**, because the fixture
cannot: ``backend/tests/unit/test_static_checks.py`` is under ``backend/`` with
a ``.py`` suffix, so a literal U+FFFD in it is a finding in it. ⭐ The tests
therefore build the character with ``"\\ufffd"`` escapes instead of writing it,
⭐ and that is worth knowing before somebody helpfully pastes a real example
into a test string. ⭐ **The file that tests a rule about a character cannot
contain the character** ⭐ — ⭐ the same reason ``no_print.py``'s own tests
cannot call ``print``.

Scope: everything the gate already treats as source ⭐ - ⭐ ``backend/``,
``frontend/src``, ``frontend/e2e``, and ``.ai/`` ⭐ - ⭐ minus the caches and build
output. ``.ai/`` is in it because ``.ai/failure-modes.md`` is where the
repository's reasoning lives, and a mangled row there loses a conclusion with no
compiler, no test and no screenshot to notice.
"""

from __future__ import annotations

from pathlib import Path

from checks.framework import CheckMeta, CheckResult, ScanContext, format_target
from checks.scan import SKIP_DIRS

NOT_UTF8 = "CHECK_SOURCE_NOT_UTF8"
REPLACEMENT = "CHECK_MOJIBAKE_REPLACEMENT_CHAR"

META = CheckMeta(
    check_id="S-15",
    slug="no-mojibake",
    title="a source file must not contain undecodable or replaced text",
    priority="P1",
    code=REPLACEMENT,
)

#: The conventional module-level name every rule exports, and the one the
#: registry test reads. Kept as an alias so the two names cannot drift ⭐ - ⭐ and
#: ``git_tracked.py`` has the same pair, for the same reason: a rule that emits
#: two codes still has to name one of them here.
CODE = REPLACEMENT

#: The character a decoder emits when it has already lost the original, and the
#: character a human pastes in from a page that had already lost it. It is not a
#: legitimate character in any of this repository's prose, which is why there is
#: no allow-list.
REPLACEMENT_CHAR = "\ufffd"

#: (root, suffixes). The roots are the trees the gate already reads; the
#: suffixes keep the walk cheap and keep generated files out.
#:
#: ⭐ **Fixed list, not "everything under the repo".** ⭐ A rule that walks the
#: whole checkout has to know about ``.git``, ``node_modules``, ``dist``,
#: ``.venv``, ``playwright-report`` and whatever comes next ⭐ - ⭐ and every one of
#: those is a place this rule would fire on somebody else's bytes. ⭐
#: ``SKIP_DIRS`` covers most of it and ``frontend.files()`` covers the rest, ⭐ but
#: the honest shape is a list of trees that each mean "source".
#:
#: ⭐⭐ **The repository root's own Markdown was missing, and the rule found it the
#: first time it ran** ⭐⭐ — ⭐ `README.zh-CN.md` had three U+FFFD in it ⭐⭐ ⭐, and
#: ⭐⭐ **a README is the single most-read file in the repository** ⭐⭐. ⭐ ⭐ The
#: ⭐⭐ first version of this rule scanned ``.ai/`` ⭐⭐ ⭐ — ⭐⭐ which is where the
#: ⭐⭐ reasoning lives ⭐⭐ ⭐ - ⭐⭐ and it still let a mangled sentence through in
#: ⭐⭐ the one file every visitor sees first ⭐⭐. ⭐⭐ ⭐ ⭐ The three roots were
#: ⭐⭐⭐ chosen from where I expected defects ⭐⭐⭐ rather than from where a
#: ⭐⭐⭐ mangled byte can actually land ⭐⭐⭐.
#: ⭐⭐ ⭐ **A rule's scope is a claim about where the defect can occur, ⭐ and the
#: ⭐⭐ ⭐ cheapest way to get it wrong is to enumerate the places you have looked.**
_ROOTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("backend", (".py",)),
    (".ai", (".md",)),
    ("frontend/src", (".ts", ".tsx", ".js", ".jsx", ".css", ".html")),
    ("frontend/e2e", (".ts",)),
)

#: Individual files at the repository root, named exactly.
#:
#: ⭐⭐ **A separate constant, and the first version hung these names off the
#: ⭐⭐ suffix tuple with an 「empty means by name」 convention** ⭐⭐ ⭐ — ⭐⭐ and the
#: ⭐⭐ mutation check left it alive ⭐⭐⭐ ⭐: ⭐⭐ the tuple was
#: ⭐⭐ ⭐⭐ ``(".", ("README.md", "CONTRIBUTING.md", …))`` ⭐⭐ ⭐⭐, ⭐⭐ ⭐⭐ so the
#: ⭐⭐ ⭐⭐ walk took the **extension** branch ⭐⭐ ⭐⭐, ⭐⭐ ⭐⭐ and ``README.md``
#: ⭐⭐ ⭐⭐ has a suffix of ``.md`` ⭐⭐ ⭐⭐ — ⭐⭐ ⭐⭐ so every root document was
#: ⭐⭐ ⭐⭐ skipped ⭐⭐ ⭐⭐ and a U+FFFD in ``README.md`` was reported **clean**
#: ⭐⭐ ⭐⭐. ⭐⭐ ⭐⭐ ⭐⭐ **A convention that makes a tuple's meaning depend on
#: ⭐⭐ ⭐⭐ whether it is empty is a convention a reader has to discover by
#: ⭐⭐ ⭐⭐ getting it wrong** ⭐⭐ ⭐⭐ ⭐⭐ — ⭐⭐ ⭐⭐ and the failure is silent
#: ⭐⭐ ⭐⭐, ⭐⭐ ⭐⭐ because 「no findings」 and 「nothing was looked at」 print the
#: ⭐⭐ ⭐⭐ same line ⭐⭐ ⭐⭐. ⭐⭐ ⭐⭐ Two constants say what each one means.
_ROOT_FILES: tuple[str, ...] = (
    "README.md",
    "README.zh-CN.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
)

#: ⭐ A long line of context in the message makes the finding usable without
#: opening the file, ⭐ and a finding about mangled text is worthless if the
#: reader cannot see the mangled text. ⭐ The whole line, not a window: ⭐ the
#: question 「which sentence did this come from」 ⭐ is answered by the sentence, ⭐
#: and a window that cuts it in half is a window that needs the file open.


def run(ctx: ScanContext) -> CheckResult:
    """Find source files that do not contain the bytes they appear to."""
    result = CheckResult()
    for path in _source_files(ctx):
        result.files.append(path)
        try:
            raw = path.read_bytes()
        except OSError as exc:  # pragma: no cover - unreadable file
            result.warn(
                NOT_UTF8,
                f"could not read `{ctx.rel(path)}`: {exc}",
                target=format_target(ctx, path),
                fix=None,
            )
            continue

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            result.error(
                NOT_UTF8,
                f"`{ctx.rel(path)}` is not valid UTF-8 ({exc.reason} at byte {exc.start})",
                target=format_target(ctx, path),
                fix="Re-save the file as UTF-8. A file in another encoding "
                "compiles locally, passes the suite, and ships text nobody "
                "else can read.",
            )
            continue

        for lineno, offset, _line in _replacement_sites(text):
            result.error(
                REPLACEMENT,
                f"`{ctx.rel(path)}:{lineno}` holds a replacement character "
                f"(U+FFFD): `{_context(text, offset)}`",
                target=format_target(ctx, path, lineno),
                fix="Restore the sentence. The file is valid UTF-8, so this "
                "character was written deliberately ⭐ - ⭐ something lost the "
                "original text before it got here, and no other tool in the gate "
                "can see that.",
            )
    return result


def _source_files(ctx: ScanContext) -> list[Path]:
    """Every governed file, sorted, with build output excluded.

    ⭐ **One skip list, not two.** ⭐ ``checks.frontend`` keeps its own
    ``_SKIP_PARTS`` because it is the UI rules' business, ⭐ and the tempting move
    here is to reach into it ⭐ - ⭐ so that a new cache directory gets excluded
    in one rule and not the other. ⭐ ``SKIP_DIRS`` already holds ``node_modules``,
    ``dist``, ``build`` and every Python cache, ⭐ and the two directories
    ``_SKIP_PARTS`` adds on top (``.vite``, ``coverage``) ⭐ live inside
    ``node_modules`` or at a source root ⭐ — ⭐ so ``SKIP_DIRS`` is
    sufficient and there is exactly one list to keep current.

    ⭐⭐ **The root's documents come from ``_ROOT_FILES`` — a flat list of exact
    ⭐⭐ names — and not from a ``"."`` entry in ``_ROOTS``** ⭐⭐⭐. ⭐⭐ A
    ⭐⭐⭐ ``"."`` root plus ``rglob`` reaches ``backend/`` and ``.ai/`` as well
    ⭐⭐⭐ ⭐ and would re-walk both ⭐⭐⭐, reporting every finding there
    ⭐⭐⭐ **twice** ⭐⭐⭐⭐ ⬏ ⭐⭐ and a duplicate finding is worse than a
    ⭐⭐⭐ missing one ⭐⭐⭐, ⭐⭐⭐ because it trains the reader to
    ⭐⭐⭐ discount the count ⭐⭐⭐⬏ ⭐⭐ and the count is the only thing a
    ⭐⭐⭐ summary line can honestly show ⭐⭐⭐⬏ ⭐⭐ Two lists, each meaning
    ⭐⭐ one thing.
    """
    found: list[Path] = []
    for relative, suffixes in _ROOTS:
        root = ctx.repo_root / relative
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            if SKIP_DIRS.intersection(path.parts):
                continue
            found.append(path)
    for name in _ROOT_FILES:
        candidate = ctx.repo_root / name
        if candidate.is_file():
            found.append(candidate)
    return sorted(found)


def _replacement_sites(text: str) -> list[tuple[int, int, str]]:
    """``(lineno, char offset, line)`` for every line holding a U+FFFD.

    One finding per line, not per character: three replacement characters in one
    mangled character are **one** defect, and reporting three would make the
    count look like a severity.
    """
    sites: list[tuple[int, int, str]] = []
    offset = 0
    for lineno, line in enumerate(text.splitlines(keepends=True), 1):
        if REPLACEMENT_CHAR in line:
            sites.append((lineno, offset, line))
        offset += len(line)
    return sites


def _context(text: str, offset: int) -> str:
    """The characters from the start of a line, whitespace collapsed.

    ⭐ **Delimited by backticks in the message, not by a line-joiner character.**
    ⭐ The first version joined lines with U+2426 ⭐ so that a snippet could not
    run into the sentence around it ⭐ - ⭐ and U+2426 is a rarer thing to read
    than a backtick. ⭐ The snippet is quoted; that is what quoting is for.
    """
    line_end = text.find("\n", offset)
    if line_end < 0:
        line_end = len(text)
    line_start = text.rfind("\n", 0, offset) + 1
    return " ".join(text[line_start:line_end].split()) or "(blank line)"


__all__ = ["CODE", "META", "NOT_UTF8", "REPLACEMENT", "run"]
