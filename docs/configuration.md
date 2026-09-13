# Configuration reference

Every key the code reads, its type, its default, and what overrides it.

Values below were read out of the source, not out of the prose: `src/parliament/config.py`
(the `resolve_*` helpers, `load_config`, `load_keys`, `save_key`,
`build_parliament_from_config`), `src/parliament/providers/__init__.py`
(`create_provider`), `src/parliament/cli.py`, `src/parliament/first_run.py`,
`src/parliament/tui.py` (`SETTINGS_FILE`), `src/parliament/render/hansard.py`
(`HansardLevel`, `DEFAULT_LEVEL`) and the five provider modules under
`src/parliament/providers/`.

Last checked against `main` at `12244bf`. If a default here disagrees with the
code, the code has moved; please open an issue.

## Where things live

`PARLIAMENT_DIR` is `~/.parliament` — `%USERPROFILE%\.parliament` on Windows —
from `Path.home()`, so it does not follow `XDG_CONFIG_HOME`.

| Path | Written by | Holds |
| --- | --- | --- |
| `~/.parliament/config.yaml` | you, the first-run wizard, the TUI's member editor | everything on this page except `save_dir` |
| `~/.parliament/settings.json` | the TUI only | `save_dir` |
| `~/.parliament/keys.env` | `parliament keys set`, when no OS keyring is available | `NAME=value` lines; `chmod 0600` on POSIX, left as-is on Windows |
| OS keyring (service `llm-parliament`) | `parliament keys set`, when a keyring is available | API keys |
| `~/.parliament/hansards/` | each run | saved Hansards, unless `save_dir` says otherwise |

`parliament keys set` **writes** to the keyring when one is available and only
falls back to `keys.env` when it is not. `load_keys` **reads** the other way
round: `keys.env` first, then the keyring only for variables the file did not
set. So if the same variable is in both, the file wins. Neither overrides a
variable already set in the process environment.

On first run, when `~/.parliament/config.yaml` does not exist, a detection
wizard checks for API keys, a reachable Ollama and system RAM, then writes a
matching preset (an interactive run shows the proposal first, and declining it
writes the mock preset). `config.example.yaml` is copied verbatim only if the
wizard raises. `parliament ask --config <path>` reads a different file instead.

`${VAR}` anywhere in the YAML is substituted from the environment before
parsing. An unset variable is **not** an error at load time: the raw text is
parsed instead and the failure surfaces later, when the provider is
constructed. That fallback is all-or-nothing: if any one `${VAR}` is unset,
**none** of them are substituted, including the ones that are set.

## Precedence

Every resolved setting follows the same order, highest first:

```
CLI flag  >  environment variable  >  config.yaml  >  built-in default
```

## `parliament`

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `parliament.name` | string | — | Not read by any code. The first-run presets and `config.example.yaml` write it (`House of AI`), but nothing displays it. |
| `parliament.members` | list | **required** | `build_parliament_from_config` indexes `config["parliament"]["members"]` directly, so a missing key is a `KeyError`. |
| `parliament.members[].name` | string | **required** | Also the key each provider instance is stored under, so it must be unique. |
| `parliament.members[].provider` | string | **required** | One of `ollama`, `anthropic`, `openai`, `google`, `mock`. |
| `parliament.members[].model` | string | **required** | Also decides the member's tier — see [tiers](#tiers). |

A member's `tier` is **not** configurable: it is resolved from the model name
through `MODEL_TIERS`, and anything unlisted becomes tier 3.

## `providers`

`providers.<name>` is passed to that provider's constructor as keyword
arguments, so the accepted set is whatever that constructor takes — and an
unknown key is a `TypeError`, not a warning. It is keyed **per provider, not
per member**: two members on the same provider share one block.

| Provider | `model` | `api_key` | `base_url` | `timeout` | other |
| --- | --- | --- | --- | --- | --- |
| `ollama` | ✅ | — | ✅ `http://localhost:11434/v1` | ✅ `null` | |
| `openai` | ✅ | ✅ | ✅ `null` | ✅ `null` | |
| `anthropic` | ✅ | ✅ | — | ✅ `null` | |
| `google` | ✅ | ✅ | — | ✅ `null` | |
| `mock` | ✅ | — | — | — | none |

`mock` takes **no** keys from this block. `create_provider` constructs it with
`model` alone and drops everything else, so `providers.mock.latency_ms` (which
`MockProvider` accepts as a constructor argument, default `50`) is silently
ignored.

`openai`'s `base_url` routes requests to any OpenAI-compatible endpoint. When it
points anywhere other than OpenAI, set `api_key` in the same block to that
vendor's key (for example `api_key: ${GROQ_API_KEY}`). Left unset, the OpenAI
SDK falls back to `OPENAI_API_KEY` and sends your OpenAI credential to the
other host.

`model` comes from the member entry and is passed for you. Setting it here as
well raises `TypeError: create_provider() got multiple values for argument
'model'` before the provider is constructed, which stops `parliament ask` and
TUI startup.

`timeout` is `null` (no limit) everywhere by default. Apart from that `base_url`
case, `api_key` is usually better left out — the provider SDKs read
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `GOOGLE_API_KEY` themselves, and
`load_config` injects `keys.env` and the keyring into the environment before
anything is constructed.

```yaml
providers:
  ollama:
    base_url: http://192.168.1.10:11434/v1
    timeout: 600.0
```

## `display`

| Key | Type | Default | Overridden by |
| --- | --- | --- | --- |
| `display.show_debate` | bool | `true` | `--show-debate` / `--no-show-debate`, then `PARLIAMENT_SHOW_DEBATE` |

`PARLIAMENT_SHOW_DEBATE` is true for `1`, `true`, `yes` or `on`, compared
case-insensitively after stripping. **Anything else is false**, including
`maybe` and a typo — it is not a parse error, so `PARLIAMENT_SHOW_DEBATE=ture`
silently turns the debate view off.

## `hansard`

| Key | Type | Default | Overridden by |
| --- | --- | --- | --- |
| `hansard.level` | string | `verdict` | `--hansard <level>`, then `PARLIAMENT_HANSARD_LEVEL`; `--verbose` is an alias for `--hansard=full`, applied only when `--hansard` is absent |

| Level | Includes |
| --- | --- |
| `minimal` | recommendation only |
| `verdict` | full synthesis — consensus, split, risks, recommendation |
| `archive` | `verdict` + frontmatter + session footer |
| `full` | `archive` + first-reading and debate transcripts |

Unknown values fall back to `verdict` **and emit a `UserWarning`**, so a typo in
a flag, an env var or the YAML is visible rather than silent.

## `settings.json`

Written by the TUI's Settings dialog, and by nothing else. It is separate from
`config.yaml` because it is per-machine rather than per-parliament.

| Key | Type | Default |
| --- | --- | --- |
| `save_dir` | string | `~/.parliament/hansards` |

There is no CLI flag and no environment variable for it; to change it outside
the TUI, edit the file:

```json
{ "save_dir": "/home/you/notes/hansards" }
```

## Environment variables

| Variable | Read by | Effect |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | provider SDK | Anthropic credentials |
| `OPENAI_API_KEY` | provider SDK | OpenAI credentials |
| `GOOGLE_API_KEY` | provider SDK | Google credentials |
| `PARLIAMENT_SHOW_DEBATE` | `resolve_show_debate` | overrides `display.show_debate` |
| `PARLIAMENT_HANSARD_LEVEL` | `resolve_hansard_level` | overrides `hansard.level` |
| any `${VAR}` in the YAML | `load_config` | substituted before parsing |

## Tiers

Tiers drive Speaker assignment and the gap warning, and are internal — there is
no config key for them. `MODEL_TIERS` in `src/parliament/core/model_tiers.py`
maps model name to tier; unknown models get `DEFAULT_TIER`, which is 3.

| Tier | Label |
| --- | --- |
| 1 | frontier |
| 2 | strong |
| 3 | capable |
| 4 | small |

`detect_gap` warns when the spread between any two members exceeds one tier.
