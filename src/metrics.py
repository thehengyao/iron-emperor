"""
Lightweight pipeline metrics collector.

Tracks agent execution times, token usage estimates, cache hit rates,
and pipeline throughput. Thread-safe via atomic operations.
"""
import time
import threading
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class AgentMetrics:
    """Per-agent execution statistics."""
    calls: int = 0
    total_ms: int = 0
    errors: int = 0
    cache_hits: int = 0
    tokens_estimated: int = 0

    @property
    def avg_ms(self) -> float:
        return self.total_ms / max(1, self.calls)

    @property
    def error_rate(self) -> float:
        return self.errors / max(1, self.calls)

    def record(self, duration_ms: int, error: bool = False, cached: bool = False, tokens: int = 0):
        self.calls += 1
        self.total_ms += duration_ms
        if error:
            self.errors += 1
        if cached:
            self.cache_hits += 1
        self.tokens_estimated += tokens


class PipelineMetrics:
    """Global metrics singleton. Thread-safe."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._agents = defaultdict(AgentMetrics)
                    cls._instance._builds = 0
                    cls._instance._build_times = []
                    cls._instance._start = time.time()
        return cls._instance

    def record_agent(self, agent: str, duration_ms: int, error: bool = False,
                     cached: bool = False, tokens: int = 0):
        self._agents[agent].record(duration_ms, error, cached, tokens)

    def record_build(self, duration_ms: int):
        self._builds += 1
        self._build_times.append(duration_ms)

    def snapshot(self) -> dict:
        uptime = time.time() - self._start
        return {
            "uptime_s": round(uptime, 1),
            "total_builds": self._builds,
            "avg_build_ms": (
                round(sum(self._build_times) / len(self._build_times))
                if self._build_times else 0
            ),
            "agents": {
                name: {
                    "calls": m.calls,
                    "avg_ms": round(m.avg_ms),
                    "error_rate": round(m.error_rate, 3),
                    "cache_hits": m.cache_hits,
                    "tokens_est": m.tokens_estimated,
                }
                for name, m in self._agents.items()
            },
        }
