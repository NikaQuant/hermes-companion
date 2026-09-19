# Validation artifacts

These files are release evidence for Hermes Companion v0.3.0.

## Browser evidence

`e2e/` contains screenshots from a clean desktop/mobile workflow against local protocol-compatible Hermes fixtures. The workflow exercised authentication, six-profile health, project overview, sessions, durable SSE runs, notifications, saved prompts, controlled file staging, diagnostics, redacted backup creation, devices and audit.

## Validation records

`validation/` distinguishes three evidence classes:

- **Automated source tests** — pytest, compile, build and static release checks.
- **Protocol-fixture integration** — mock Hermes HTTP and `hermes serve` endpoints implementing the contracts used by Companion.
- **Target-host pending** — the real-Hermes smoke utility itself is fixture-validated, but Nik must still run it against the actual regular-Hermes VPS.

No fixture result should be represented as proof that the user's real providers, tools, Desktop build or Windows tasks are configured correctly.
