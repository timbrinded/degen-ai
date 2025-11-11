"""LangSmith tracing helpers for baseline loop instrumentation."""

from __future__ import annotations

import json
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

try:  # LangSmith is optional until dependencies are installed
    from langsmith import trace as _langsmith_trace  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - optional dependency
    _langsmith_trace = None

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASELINE_LOG_PATH = PROJECT_ROOT / "logs" / "langsmith_baseline.log"
DEFAULT_TAGS = ("baseline", "loop")


@dataclass
class LoopSpan(AbstractContextManager["LoopSpan"]):
    """Context manager that records LangSmith runs per loop execution."""

    loop_type: str
    tick: int
    metadata: dict[str, Any] = field(default_factory=dict)
    langgraph_phase: int = 0

    _trace_cm: Any = field(init=False, default=None)
    _run: Any = field(init=False, default=None)
    trace_id: str | None = field(init=False, default=None)
    metrics: dict[str, Any] = field(init=False, default_factory=dict)
    started_at: datetime = field(init=False)

    def __post_init__(self) -> None:
        self.started_at = datetime.now(UTC)

    def __enter__(self) -> LoopSpan:
        tags = list(DEFAULT_TAGS) + [
            f"loop:{self.loop_type}",
            f"langgraph-phase:{self.langgraph_phase}",
        ]
        metadata = {
            "loop": self.loop_type,
            "langgraph_phase": self.langgraph_phase,
            **self.metadata,
        }
        inputs = {"tick": self.tick, "loop": self.loop_type}

        if _langsmith_trace is not None:
            self._trace_cm = _langsmith_trace(
                name=f"governed_agent.{self.loop_type}_loop",
                run_type="chain",
                metadata=metadata,
                tags=tags,
                inputs=inputs,
            )
            self._run = self._trace_cm.__enter__()
            if self._run is not None:
                self.trace_id = str(getattr(self._run, "trace_id", "")) or None
        if self.trace_id is None:
            self.trace_id = f"offline-{uuid4()}"
        return self

    def record(self, **metrics: Any) -> None:
        """Attach metrics that should be saved with the run and baseline log."""
        self.metrics.update({k: v for k, v in metrics.items() if v is not None})

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[override]
        duration_ms = round((datetime.now(UTC) - self.started_at).total_seconds() * 1000, 3)
        outputs = {
            **self.metrics,
            "loop_duration_ms": duration_ms,
            "errored": exc_type is not None,
        }

        if self._run is not None and outputs:
            with suppress(Exception):
                self._run.add_outputs(outputs)

        if self._trace_cm is not None:
            self._trace_cm.__exit__(exc_type, exc, tb)

        if self.trace_id:
            _append_baseline_log(
                loop=self.loop_type,
                tick=self.tick,
                trace_id=self.trace_id,
                duration_ms=duration_ms,
                metrics=outputs,
            )
        return False


def loop_span(
    loop_type: str,
    tick: int,
    *,
    metadata: dict[str, Any] | None = None,
    langgraph_phase: int = 0,
) -> LoopSpan:
    """Create a LoopSpan context manager for the given loop and tick."""

    return LoopSpan(
        loop_type=loop_type,
        tick=tick,
        metadata=metadata or {},
        langgraph_phase=langgraph_phase,
    )


def _append_baseline_log(
    *, loop: str, tick: int, trace_id: str, duration_ms: float, metrics: dict[str, Any]
) -> None:
    """Persist LangSmith trace metadata to logs/langsmith_baseline.log."""

    BASELINE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "loop": loop,
        "tick": tick,
        "trace_id": trace_id,
        "duration_ms": duration_ms,
        "metrics": metrics,
    }
    with BASELINE_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


__all__ = ["loop_span", "LoopSpan"]
