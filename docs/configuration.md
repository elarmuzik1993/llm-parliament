# Configuration reference

Every key the code reads, its type, its default, and what overrides it.

Values below were read out of the source, not out of the prose: `src/parliament/config.py`
(the `resolve_*` helpers, `load_config`, `build_parliament_from_config`),
`src/parliament/tui.py` (`SETTINGS_FILE`), `src/parliament/render/hansard.py`
(`HansardLevel`) and the four provider `__init__` signatures under
`src/parliament/providers/`.

## Where things live

`PARLIAMENT_DIR` is `~/.parliament` — `%USERPROFILE%\.parliament` on Windows —
from `Path.home()`, so it does not follow `XDG_CONFIG_HOME`.

| Path | Written by | Holds |
| --- | --- | --- |
| `~/.parliament/config.yaml` | you, `parliament members`, the TUI | everything on this page except `save_dir` |
| `~/.parliament/settings.json` | the TUI only | `save_dir` |
| `~/.parliament/keys.env` | `parliament keys set`, when no OS keyring is available | `NAME=value` lines, `chmod 0600` |
| OS keyring (service `llm-parliament`) | `parliament keys set` | API keys, preferred over `keys.env` |
| `~/.parliament/hansards/` | each run | saved Hansards, unless `save_dir` says otherwise |

On first run `config.example.yaml` is copied to `~/.parliament/config.yaml`.
`parliament ask --config <path>` reads a different file instead.

`${VAR}` anywhere in the YAML is substituted from the environment before
parsing. An unset variable is **not** an error at load time: the raw text is
parsed instead and the failure surfaces later, when the provider is
constructed.

## Precedence

Every resolved setting follows the same order, highest first:

```
CLI flag  >  environment variable  >  config.yaml  >  built-in default
```

## `parliament`

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `parliament.name` | string | — | Display name for the house. |
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
| `openai` | ✅ | ✅ | — | ✅ `null` | |
| `anthropic` | ✅ | ✅ | — | ✅ `null` | |
| `google` | ✅ | ✅ | — | ✅ `null` | |
| `mock` | ✅ | — | — | — | `latency_ms`, default `50` |

`model` comes from the member entry and is passed for you; setting it here as
well would be passed twice.

`timeout` is `null` (no limit) everywhere by default. `api_key` is usually
better left out — the provider SDKs read `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
and `GOOGLE_API_KEY` themselves, and `load_config` injects `keys.env` and the
keyring into the environment before anything is constructed.

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
| `hansard.level` | string | `minimal` | `--hansard <level>`, then `PARLIAMENT_HANSARD_LEVEL` |

| Level | Includes |
| --- | --- |
| `minimal` | recommendation only |
| `verdict` | full synthesis — consensus, split, risks, recommendation |
| `archive` | `verdict` + frontmatter + session footer |
| `full` | `archive` + first-reading and debate transcripts |

Unknown values fall back to `minimal` **and emit a `UserWarning`**, so a typo in
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
