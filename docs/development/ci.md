# CI strategy

This repository uses a tiered CI strategy to keep developer feedback fast while preserving full validation coverage.

## Workflows and triggers

1. `.github/workflows/ci-fast.yml`
- Trigger: `push` to `codex/**` or `feature/**`, plus `workflow_dispatch`.
- Goal: fast feedback (target under 10-15 minutes).
- Jobs:
  - Windows fast lint + focused router/voice/core/server tests.
  - Rust clippy + Rust tests.

2. `.github/workflows/ci-pr.yml`
- Trigger: `pull_request` targeting `main`, plus `workflow_dispatch`.
- Goal: serious pre-merge validation without running the heaviest full suite.
- Jobs:
  - Lint (ruff).
  - Windows-specific voice/router validation.
  - Linux/POSIX validation for security/telemetry/core/cli.
  - Rust clippy + Rust tests.

3. `.github/workflows/ci-full.yml`
- Trigger: `push` to `main`, `workflow_dispatch`, and nightly `schedule`.
- Schedule: daily at 03:00 UTC.
- Goal: full suite coverage (can be long-running).
- Jobs:
  - Full Windows Python suite.
  - Full Linux Python suite.
  - Rust clippy + Rust tests.

## Test split by platform

Windows jobs run tests focused on desktop/voice/router runtime, for example:
- `tests/scripts/test_windows_hotkey_voice_phase1.py`
- `tests/speech`
- `tests/tools`
- `tests/server`

Windows commands exclude incompatible or expensive classes:
- `not linux_only and not posix_only and not live and not cloud`

Linux jobs run Linux/POSIX and portable suites, for example:
- `tests/security`
- `tests/telemetry`
- `tests/core`
- `tests/cli`

Linux commands exclude incompatible or expensive classes:
- `not windows_only and not live and not cloud`

## Fast CI command

Fast CI uses:
- `uv run ruff check src tests`
- `uv run pytest tests/speech tests/tools tests/server -q -m "not live and not cloud and not slow and not windows_only and not linux_only and not posix_only"`

## Manual full CI run

To launch full CI manually:
1. Open GitHub Actions.
2. Select **CI Full**.
3. Click **Run workflow** (`workflow_dispatch`).

## Markers for new tests

When adding tests, mark platform/runtime requirements explicitly in pytest markers:
- `windows_only`: requires Windows.
- `linux_only`: requires Linux.
- `posix_only`: requires POSIX semantics.
- `slow`: long-running test.
- `live`: depends on live runtime/service.
- `cloud`: requires cloud API keys or remote services.
- `external_node`: requires external Node runtime/tooling.

This prevents cross-platform mixing and keeps each CI level reliable and intentional.

## Execution controls

All CI workflows include:
- Concurrency cancellation per branch/ref:
  - `group: ${{ github.workflow }}-${{ github.ref }}`
  - `cancel-in-progress: true`
- Job timeouts:
  - Fast CI jobs: up to 15 min.
  - PR CI jobs: up to 30 min.
  - Full CI jobs: up to 60 min.
- Dependency caching:
  - `astral-sh/setup-uv` cache enabled for Python/uv dependencies.
  - Cargo cache for Rust jobs.
  - Frontend npm cache remains in `.github/workflows/frontend.yml`.
