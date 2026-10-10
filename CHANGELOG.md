# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Windows redirected output** — `parliament doctor` and `parliament ask` no longer crash with UnicodeEncodeError when stdout/stderr is redirected or piped on Windows (cp1252). Streams are reconfigured to UTF-8 with errors="replace" at CLI startup when needed. Fixes #74.


### Changed

- **Capability assessments across providers** — distinguish assessed large gaps,
  comparable rated members and missing ratings. Unassessed models are reported
  explicitly in warnings and Hansard JSON's `unrated_members`, rather than
  manufacturing a rated gap or silently disappearing. Fallback tier 3 remains
  a Speaker-selection assumption; explicit mock tiers remain synthetic ratings.
- **Unassessed OpenRouter variants** — unfamiliar tuning and revision IDs remain
  unassessed rather than inheriting a known model's capability rating.

### Added

- **OpenRouter first-run preset** — detect `OPENROUTER_API_KEY` and propose
  three models from Anthropic, OpenAI, and Google using one account. Existing
  two- and three-provider setups keep their direct presets, and three usable
  local models take priority over OpenRouter. Otherwise OpenRouter precedes
  mixed, single-provider and mock presets. Its model IDs resolve to the same
  tiers as their direct counterparts. Fixes #38.

- **Groq and Mistral providers** — use `provider: groq` or `provider: mistral`
  directly, with dedicated key management, TUI selection, and doctor checks
  for configured members.
  Fixes #48.

- **`openrouter` provider** — OpenRouter speaks the OpenAI API at its own
  address, so it needs no class of its own: it reuses `OpenAIProvider` with the
  address and the `OPENROUTER_API_KEY` variable read from its
  `model_catalog.OPENAI_COMPATIBLE` row. A member can now name
  `provider: openrouter` instead of pointing `openai` at a `base_url`, and
  because `openrouter` is in `KEY_PROVIDERS`, `parliament keys set openrouter`,
  `keys list`, the TUI's `/key`, and the doctor's key check all follow with no
  further wiring. The compatible-provider registry is shared with Groq and Mistral.
