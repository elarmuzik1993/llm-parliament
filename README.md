# LLM Parliament

Multi-agent debate for better AI decisions. Research-backed, local-first.

Three AI models debate your question through a parliamentary process — First Reading, Debate, Division — and deliver a structured verdict: Consensus, Split, Risks, Recommendation.

Built on multi-agent debate — a technique shown to improve AI accuracy by 7-15% in research (Liang et al. 2023, Chen et al. 2023).

## Quick Start

```bash
pip install llm-parliament[cli]

# Local (free, requires Ollama)
parliament ask "PostgreSQL or MongoDB for analytics?"

# Cloud (best quality, requires API keys)
parliament ask "question" --config config.cloud.yaml

# Dev/testing (instant, no setup)
parliament ask "question" --mock
```

## License

AGPLv3
