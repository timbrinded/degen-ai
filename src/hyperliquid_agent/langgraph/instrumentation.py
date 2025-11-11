"""LangGraph node instrumentation helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

try:  # LangSmith is optional until dependencies are installed
    from langsmith import trace as _langsmith_trace  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - optional dependency
    _langsmith_trace = None


@contextmanager
def node_trace(
    node_name: str,
    *,
    metadata: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Context manager that mirrors `loop_span` but scoped to LangGraph nodes."""

    if _langsmith_trace is None:
        yield None
        return

    cm = _langsmith_trace(
        name=f"langgraph.nodes.{node_name}",
        run_type="chain",
        metadata=metadata or {},
        tags=["langgraph", f"node:{node_name}"],
        inputs=inputs or {},
    )
    run = cm.__enter__()
    try:
        yield run
    finally:
        cm.__exit__(None, None, None)


def summarize_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Return lightweight metadata about a patch for logging/tracing."""

    summary: dict[str, Any] = {
        "keys": sorted(patch.keys()),
        "size": len(patch),
    }
    for key, value in patch.items():
        if isinstance(value, dict):
            summary[f"{key}_keys"] = sorted(value.keys())
    return summary


__all__ = ["node_trace", "summarize_patch"]
