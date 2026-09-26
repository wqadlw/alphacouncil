# Contributing to AlphaCouncil

Thanks for your interest. This project is developed under a **spec-driven,
multi-role workflow** — the same rules apply to human contributors and AI agents.

**Before you write any code, read [`.ai/constitution.md`](.ai/constitution.md).**
It defines the non-negotiable rules. Changes that violate it will be rejected
regardless of whether they work.

---

## Quick start

```bash
git clone https://github.com/OWNER/alphacouncil.git
cd alphacouncil

make install          # create .venv and install dependencies
make install-hooks    # install pre-commit hooks
cp .env.example .env  # fill in your keys

make check            # lint + typecheck + tests — must be green before you start
```

Requires Python 3.12+ and, for the full stack, Docker.

## The workflow

```
① Spec      →  write .ai/specs/NNN-<feature>/{spec,plan,tasks}.md
② Implement →  work through tasks one at a time
③ Test      →  unit tests are the author's job; acceptance tests are independent
④ Review    →  a reviewer reads the diff and files issues (read-only)
⑤ Merge     →  CI green + review passed + human approval
```

**No spec, no feature.** If you want to change behaviour, open a spec first —
even for small changes, a few lines in `spec.md` is enough.

## Before opening a pull request

Run the same gates CI runs:

```bash
make check        # ruff + mypy + pytest
make precommit    # all pre-commit hooks
```

Checklist:

- [ ] All functions have complete type annotations (`mypy --strict` passes)
- [ ] New behaviour is covered by tests
- [ ] Coverage did not drop below 80% (90% for `retrieval/` and `graph/`)
- [ ] No `print()`, no bare `except`, no hardcoded config values
- [ ] No secrets, no large files, no local data
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
- [ ] The PR description states **what changed**, **why**, and **how you verified it**

## Changing retrieval logic

Any change that affects recall or ranking **must** include before/after RAGAS
metrics in the PR description. This is constitution §4.3 — retrieval quality is
the core of this project and we do not accept unmeasured changes to it.

```bash
cd backend && pytest tests/eval -m eval
```

## Reporting bugs

Open an issue with:

- What you expected
- What happened
- A minimal reproduction (command + input + output)
- Your environment (`python --version`, OS, commit SHA)

## Proposing a new dependency

Do not add a dependency in a PR. Open an issue first using the template in
[`.ai/logs/README.md`](.ai/logs/README.md) — explain why the standard library or
an existing dependency cannot do the job, and include evidence of the package's
maintenance activity.

## Code of conduct

Be direct about code, generous about people. Review the code, not the author.

## Licence

By contributing, you agree your contributions are licensed under the MIT Licence.
