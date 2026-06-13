"""Test runner / orchestrator for LLM-based end-to-end tests."""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from .config import TestConfig
from .client import CXHMSClient
from .judge import JudgeAgent
from .judge_tools import ToolExecutor
from .metrics import MetricsCollector


@dataclass
class StepResult:
    """Result of a single step within a scenario."""

    name: str = ""
    passed: bool = False
    score: float = 0.0
    response_time_ms: float = 0.0
    ttft_ms: float = 0.0
    tps: float = 0.0
    details: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class ScenarioResult:
    """Result of an entire scenario."""

    name: str = ""
    description: str = ""
    passed: bool = False
    score: float = 0.0
    metrics: dict = field(default_factory=dict)
    steps: list[StepResult] = field(default_factory=list)
    error: str | None = None


ScenarioFunc = Callable[
    [CXHMSClient, JudgeAgent, MetricsCollector, TestConfig],
    Awaitable[ScenarioResult],
]


class TestRunner:
    """Orchestrates the execution of LLM E2E test scenarios."""

    def __init__(self, config: TestConfig | None = None) -> None:
        self.config = config or TestConfig()
        self._results: list[ScenarioResult] = []

    @property
    def results(self) -> list[ScenarioResult]:
        return list(self._results)

    async def run_scenario(self, scenario: ScenarioFunc) -> ScenarioResult:
        """Execute a single scenario function and return its result.

        The scenario callable receives (client, judge, metrics_collector, config)
        and must return a ScenarioResult.
        """
        metrics = MetricsCollector()

        async with CXHMSClient(
            base_url=self.config.cxhms_base_url,
            timeout=self.config.chat_timeout,
        ) as client:
            tool_executor = ToolExecutor(client)
            judge = JudgeAgent(self.config, tool_executor)

            try:
                result = await scenario(client, judge, metrics, self.config)
            except Exception as exc:
                result = ScenarioResult(
                    name=getattr(scenario, "__name__", str(scenario)),
                    description="",
                    passed=False,
                    score=0.0,
                    metrics=metrics.get_summary(),
                    steps=[],
                    error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                )
            finally:
                await judge.close()

        self._results.append(result)
        return result

    async def run_all(self, scenarios: list[ScenarioFunc]) -> list[ScenarioResult]:
        """Execute all scenarios sequentially and return their results."""
        self._results.clear()
        for scenario in scenarios:
            await self.run_scenario(scenario)
        return self.results
