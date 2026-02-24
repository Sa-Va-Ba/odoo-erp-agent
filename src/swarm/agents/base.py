"""Base agent interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import AgentResult, NormalizedInterview


class SwarmAgent(ABC):
    name: str = "agent"

    @abstractmethod
    def run(self, interview: NormalizedInterview) -> AgentResult:
        raise NotImplementedError
