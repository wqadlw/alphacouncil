# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately via GitHub's [Security Advisories](https://github.com/OWNER/alphacouncil/security/advisories/new),
or email the maintainers. Include:

- A description of the issue and its impact
- Steps to reproduce
- Affected version or commit SHA
- Any suggested mitigation

We aim to acknowledge reports within 72 hours and to publish a fix or mitigation
within 30 days for confirmed issues.

## Scope

AlphaCouncil is a research tool. The following are in scope:

- **Secret leakage** — credentials reaching logs, API responses, or the repository
- **Prompt injection leading to data exfiltration** — a malicious document in the
  corpus causing the agent to leak data or call unintended tools
- **SQL injection via Text-to-SQL** — the structured retrieval route generates SQL
  from natural language; bypassing the SELECT-only guard is a critical issue
- **Remote code execution** — via document parsing or tool invocation
- **Denial of service** — inputs that cause unbounded agent loops or runaway cost

Out of scope:

- The accuracy of research output (this is not a security property)
- Vulnerabilities in third-party services (report those upstream)
- Issues requiring a already-compromised host

## Security design notes

The following controls are intentional and should not be weakened:

| Control | Location | Rationale |
|---|---|---|
| SELECT-only SQL guard | `retrieval/structured.py` | Text-to-SQL output is LLM-generated and must be treated as untrusted |
| Secret masking | `core/config.py` uses `SecretStr` | Prevents credentials appearing in logs or tracebacks |
| Cost and step ceilings | `core/config.py` (`max_agent_steps`, `max_cost_usd_per_run`) | Bounds the blast radius of a runaway loop |
| Secret scanning in CI | `.github/workflows/ci.yml` | Blocks commits containing credentials |
| No brokerage integration | by design | The system cannot place orders, so it cannot be weaponised to trade |

## Handling credentials

- Never commit `.env`. It is gitignored, and CI runs gitleaks.
- Use scoped keys with the lowest privilege that works.
- Rotate any key that has ever been committed, even briefly — history is public.

## Supported versions

The project is pre-1.0; only the `main` branch receives security fixes.
