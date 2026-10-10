# Hansard JSON schema

`parliament ask --json` prints a complete Hansard: the question, the members
who debated it, each phase response, and the Speaker's final synthesis. The JSON
shape mirrors the dataclasses in `src/parliament/core/types.py` and is stable
for simple shell pipelines.

Generate a sample with:

```bash
parliament ask "Should we split this service?" --mock --json
```

## Top-level object

| Field | Type | Description |
| --- | --- | --- |
| `bill` | `Bill` | The question submitted to Parliament. |
| `members` | `Member[]` | The models configured for the session. |
| `first_reading` | `Response[]` | Each member's initial answer to the bill. |
| `debate` | `Response[]` | Each member's critique after seeing the other first-reading responses. |
| `synthesis` | `Synthesis` | The Speaker's final structured verdict. |
| `id` | `string` | UUID for this Hansard. |
| `created_at` | `string` | ISO-8601 timestamp for when the session was created. |
| `duration_ms` | `number` | Total wall-clock duration in milliseconds. |
| `degraded` | `boolean` | `true` when the verdict came from fewer members than configured, because one or more members failed with a provider error. |
| `unrated_members` | `string[]` | Names of configured members without an assessed capability rating. Their tier 3 is a Speaker-selection assumption. |

### `unrated_members`

New sessions explicitly report every unassessed real model, including members
that later fail or drop out. This flag is independent of `degraded`: complete
participation does not establish that model capabilities were assessed. Join
these names to `members[].name` to obtain provider and model IDs. Explicit
mock tiers are synthetic ratings and are not flagged as unrated.

```json
{"unrated_members": ["Mystery"]}
```

Known members may also have a large capability gap while unrated members are
present; neither warning clears the other. An empty array means all configured
members had ratings. Older records omit this field; the reader defaults it to
an empty list for compatibility, but absence in old JSON is not proof of rating
coverage. Endpoint context is runtime-only and excluded from member JSON.

### `degraded`

Degraded mode is intended behaviour: if a provider times out or runs out of
quota, the remaining members carry on and you still get a verdict. What it does
*not* tell you on its own is how many members that verdict came from, and a
two-member verdict is a weaker thing than a three-member one. `degraded` makes
that visible to a consumer without re-deriving it from the response arrays.

Check it before trusting a verdict in a script or an agent tool call:

```bash
parliament ask "Should we split this service?" --json \
  | jq -e '.degraded' >/dev/null \
  && echo "warning: partial debate" \
  || echo "all members responded"
```

A debate that is **cancelled** — Ctrl-C, an enclosing timeout, a disconnected
client — does not produce a Hansard at all. `ask()` re-raises
`asyncio.CancelledError` rather than returning a partial verdict, so a
cancelled call can never be mistaken for a confident one.

## `Bill`

| Field | Type | Description |
| --- | --- | --- |
| `content` | `string` | The full question text passed to `parliament ask`. |
| `title` | `string` | A short title. Defaults to the first 60 characters of `content`. |

## `Member`

| Field | Type | Description |
| --- | --- | --- |
| `name` | `string` | Display name used in debate output. |
| `provider_name` | `string` | Provider key, such as `ollama`, `anthropic`, `openai`, `google`, or `mock`. |
| `model` | `string` | Provider model identifier. |
| `tier` | `number` | Assessed capability tier, or assumed tier 3 for names in `unrated_members`. **Lower is stronger** — the Speaker is chosen from the lowest tier present. |

## `Response`

`first_reading` and `debate` are arrays of `Response` objects.

| Field | Type | Description |
| --- | --- | --- |
| `member_name` | `string` | Name of the member that produced this response. |
| `content` | `string` | The response text. |
| `phase` | `"first_reading" \| "debate"` | Phase that produced the response. |
| `duration_ms` | `number` | Duration for this member response in milliseconds. |

## `Synthesis`

The `synthesis` object is the Speaker's Division output, parsed into the same
four parts shown in the normal terminal verdict.

| Field | Type | Description |
| --- | --- | --- |
| `speaker_name` | `string` | Who wrote the final synthesis: a member, or the outside Speaker from `parliament.speaker`. Not in `members` means it did not debate. |
| `consensus` | `string` | Points the members mostly agreed on. |
| `split` | `string` | Material disagreements or trade-offs. |
| `risks` | `string` | Risks, caveats, and failure modes. |
| `recommendation` | `string` | Final recommended course of action. |
| `raw` | `string` | Full unparsed Speaker output before the four fields above were extracted. |

## Degraded sessions

`first_reading` and `debate` may hold **fewer entries than `members`**. When a
provider fails, that member is dropped and the session continues as long as at
least two members respond — so a Hansard can name three members but carry only
two responses.

Two consequences for consumers:

- Join on `member_name`, never by array index. `members[i]` and
  `first_reading[i]` are not guaranteed to be the same member.
- The failure *reason* is not in the JSON. It is written to **stderr**, so
  capture that stream if you need it: `parliament ask ... --json 2>errors.log`.

To detect a degraded run in a script:

```bash
parliament ask "Should we split this service?" --json > hansard.json
jq -e '(.members | length) == (.first_reading | length)' hansard.json >/dev/null \
  || echo "warning: one or more members dropped out"
```

## Example shape

```json
{
  "bill": {
    "content": "Should we split this service?",
    "title": "Should we split this service?"
  },
  "members": [
    {
      "name": "Mock-A",
      "provider_name": "mock",
      "model": "mock-v1",
      "tier": 3
    }
  ],
  "first_reading": [
    {
      "member_name": "Mock-A",
      "content": "Initial analysis...",
      "phase": "first_reading",
      "duration_ms": 12
    }
  ],
  "debate": [
    {
      "member_name": "Mock-A",
      "content": "Critique...",
      "phase": "debate",
      "duration_ms": 9
    }
  ],
  "synthesis": {
    "speaker_name": "Mock-1",
    "consensus": "...",
    "split": "...",
    "risks": "...",
    "recommendation": "...",
    "raw": "..."
  },
  "id": "b0a5f3b0-1111-4222-8333-444455556666",
  "created_at": "2026-01-01T12:00:00+00:00",
  "duration_ms": 1234,
  "degraded": false,
  "unrated_members": []
}
```

## Practical `jq` recipes

Print only the final recommendation:

```bash
parliament ask "Should we split this service?" --json \
  | jq -r .synthesis.recommendation
```

List the configured members and models:

```bash
parliament ask "Which queue should we use?" --json \
  | jq -r '.members[] | "\(.name): \(.provider_name)/\(.model)"'
```

Print each first-reading response with its member name:

```bash
parliament ask "Is this architecture too complex?" --json \
  | jq -r '.first_reading[] | "\(.member_name): \(.content)"'
```

Print debate critiques in phase order:

```bash
parliament ask "Should this be async?" --json \
  | jq -r '.debate[] | "\(.member_name): \(.content)"'
```
