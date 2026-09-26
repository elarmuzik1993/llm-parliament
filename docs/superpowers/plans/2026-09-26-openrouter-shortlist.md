# Issue #37 shortlist proposal

Status: draft, not posted. The GitHub connector returned HTTP 403; no browser
session was available. The shortlist is not implemented pending discussion.

The following text is ready to post to
https://github.com/elarmuzik1993/llm-parliament/issues/37.

---

Thanks for the detailed feedback. I will use the provider-scoped normalization
rule, require the provider at every tier lookup, remove the three duplicate tier
entries, and exclude unclassified models from gap warnings while keeping their
numeric fallback tier.

For the shortlist, I checked https://openrouter.ai/api/v1/models on 2026-09-26.
All of these IDs are currently listed:

| Group | Proposed IDs |
| --- | --- |
| Frontier (existing project tiers) | `anthropic/claude-opus-4.6`, `openai/gpt-4o`, `google/gemini-2.5-pro` |
| Strong mid-tier | `anthropic/claude-sonnet-4.6`, `openai/gpt-4o-mini`, `google/gemini-2.5-flash` |
| Free candidates | `qwen/qwen3.8-27b:free`, `google/gemma-4-31b-it:free` |

The two free candidates currently report both prompt and completion pricing as
`0`. Their capability tiers still need assessment; free pricing alone does not
establish capability. The previously mentioned
`meta-llama/llama-3.3-70b-instruct:free` was not in the current response, so I would
not put it in the shortlist as an available free option.

I propose showing the small shortlist above the complete live catalog,
deduplicating IDs, and retaining custom entry. On a successful fetch, only
shortlist IDs present in the live response should be shown; free labels should
be checked against current pricing rather than treated as permanent. The
original API IDs remain unchanged throughout.

Does this list and behavior look right? I am working on the tier regression fix
first; the shortlist and the new free-model tier entries can follow once we
agree on them.
