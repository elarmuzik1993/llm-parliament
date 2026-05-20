# Contributing to LLM Parliament

Thanks for taking the time to contribute.

## Before you start

- Check [open issues](https://github.com/elarmuzik1993/llm-parliament/issues)
  to avoid duplicating work.
- For significant changes, open an issue first to discuss the approach.
- Read `AGENTS.md` — it covers the architecture, conventions, and key files
  you need to know before touching the code.

## Setup

```bash
git clone https://github.com/elarmuzik1993/llm-parliament.git
cd llm-parliament
pip install -e ".[dev]"
```

## Before submitting a PR

```bash
python -m pytest -q    # all 400 tests must pass
ruff check .           # must be clean
```

## What makes a good PR

- **Focused** — one logical change per PR.
- **Tested** — new behaviour has tests; bug fixes include a regression test.
- **Clean** — no debug prints, no commented-out code, ruff clean.
- **Described** — PR description explains *why*, not just *what*.

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
For security issues, follow [SECURITY.md](SECURITY.md) instead.

## Feature requests

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).
