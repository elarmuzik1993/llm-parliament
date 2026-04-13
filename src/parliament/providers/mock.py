"""Mock provider — fake responses for testing. No API calls."""

from __future__ import annotations

import asyncio

from parliament.providers.base import Provider


class MockProvider(Provider):
    name = "mock"

    def __init__(self, model: str = "mock-v1", latency_ms: int = 50) -> None:
        self.model = model
        self._latency_ms = latency_ms

    async def generate(self, prompt: str, system: str | None = None) -> str:
        # Simulate realistic latency
        await asyncio.sleep(self._latency_ms / 1000)

        # Detect Speaker synthesis prompt by looking for the section headers instruction
        if "CONSENSUS" in prompt and "RECOMMENDATION" in prompt and "Speaker" in prompt:
            return self._mock_synthesis()
        return f"[Mock {self.model}] Analysis of: {prompt[:100]}..."

    def _mock_synthesis(self) -> str:
        return (
            "CONSENSUS:\nAll analysts agree on the core approach.\n\n"
            "SPLIT:\nMinor disagreement on implementation details.\n\n"
            "RISKS:\n- Integration complexity\n- Timeline pressure\n\n"
            "RECOMMENDATION:\nProceed with the majority approach."
        )
