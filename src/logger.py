"""
Structured JSON logger for pipeline observability.

Outputs one JSON object per log line — parseable by jq, Loki, CloudWatch.
Timestamps are ISO-8601 UTC. Agent context is always present.
"""
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any


class PipelineLogger:
    """Structured logger that writes JSON lines to stderr."""

    def __init__(self, pipeline_id: str = "", stream=None):
        self.pipeline_id = pipeline_id
        self.stream = stream or sys.stderr
        self._start = time.monotonic()

    def _emit(self, level: str, event: str, agent: str = "", **fields):
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            "pipeline": self.pipeline_id,
            "elapsed_ms": int((time.monotonic() - self._start) * 1000),
        }
        if agent:
            record["agent"] = agent
        record.update(fields)
        self.stream.write(json.dumps(record) + "\n")
        self.stream.flush()

    def info(self, event: str, agent: str = "", **kw):
        self._emit("info", event, agent, **kw)

    def warn(self, event: str, agent: str = "", **kw):
        self._emit("warn", event, agent, **kw)

    def error(self, event: str, agent: str = "", **kw):
        self._emit("error", event, agent, **kw)

    def agent_start(self, agent: str, task: str):
        self._emit("info", "agent.start", agent, task=task)

    def agent_done(self, agent: str, duration_ms: int, **result_fields):
        self._emit("info", "agent.done", agent, duration_ms=duration_ms, **result_fields)

    def agent_error(self, agent: str, error: str, duration_ms: int):
        self._emit("error", "agent.error", agent, error=error, duration_ms=duration_ms)

    def cache_hit(self, agent: str):
        self._emit("info", "cache.hit", agent)

    def retry(self, agent: str, attempt: int, delay_ms: int, reason: str):
        self._emit("warn", "api.retry", agent, attempt=attempt, delay_ms=delay_ms, reason=reason)

    def pipeline_done(self, status: str, total_ms: int, parts: int = 0, cost_usd: float = 0):
        self._emit("info", "pipeline.done", status=status, total_ms=total_ms, parts=parts, cost_usd=cost_usd)
