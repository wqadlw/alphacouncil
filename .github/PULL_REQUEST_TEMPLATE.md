## What does this change?

<!-- One or two sentences. What behaviour is different after this PR? -->

## Why?

<!--
The reasoning, not the diff. A reviewer can read the diff; they cannot read
your mind. If this supersedes a decision in .ai/memory/decisions.md, say so and
explain why the decision should change.
-->

## How was it verified?

<!--
Concrete commands and their results. "It works" is not verification.
-->

```bash
# e.g.
cd backend && pytest tests/unit -m unit
ruff check . && mypy --config-file pyproject.toml src tests
```

## Spec

<!-- Link the spec this implements. Non-trivial changes require one. -->

- Spec: `.ai/specs/NNN-<name>/spec.md`
- Closes #

## Checklist

- [ ] I read `.ai/constitution.md` and this change complies with it
- [ ] All functions have complete type annotations; `mypy --strict` passes
- [ ] New behaviour is covered by tests
- [ ] `make check` passes locally
- [ ] No `print()`, no bare `except`, no hardcoded configuration
- [ ] No secrets, large files, or local data included
- [ ] Documentation updated if behaviour or interfaces changed
- [ ] Commit messages follow Conventional Commits

## Retrieval impact (required if retrieval logic changed)

<!--
Constitution §4.3: any change affecting recall or ranking must carry before/after
RAGAS metrics. Delete this section if retrieval is untouched.
-->

| Metric | Before | After |
|---|---|---|
| context_precision | | |
| context_recall | | |
| faithfulness | | |

## Screenshots / traces

<!-- For UI changes or agent-behaviour changes, include a screenshot or a Langfuse trace link. -->
