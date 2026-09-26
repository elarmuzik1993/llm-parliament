# State

_Updated 2026-09-26_

## Now
- Issue #37 tier fix implemented: provider-scoped OpenRouter identity resolution,
  required provider arguments, known-only capability-gap warnings, and regression
  coverage for config, TUI, runtime Speaker selection and unchanged API IDs.
- `bash scripts/verify.sh` passed with the project `.venv` using Git Bash on Windows
  (ruff, mypy, full pytest). Human commit identity verified as Kun Ren.

## Next
1. Post and discuss `docs/superpowers/plans/2026-09-26-openrouter-shortlist.md` on #37.
   User authorized posting, but the connector returned 403 and no browser is available.
2. Implement the shortlist after agreement; assess tiers of the two free candidates.
3. OpenRouter docs/doctor #39 and wider roadmap #15 remain separate work.

## Decisions
- Preserve API/config model IDs. Normalize only OpenRouter tier identities by removing
  vendor/ and :variant, converting Claude version dots, then applying exceptional aliases.
- Unknown models keep numeric tier 3 but cannot establish or appear in gap warnings.
- Existing first-run presets and live discovery remain unchanged; shortlist is pending.

## Known issues
- GitHub integration cannot post to #37 (403 Resource not accessible by integration).
- Shortlist draft was checked against OpenRouter's public catalog on 2026-09-26;
  availability and free pricing must be rechecked before implementing it.
