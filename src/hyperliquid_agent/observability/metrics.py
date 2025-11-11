"""Observability helpers for LangGraph runtime metrics."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any


class LangGraphMetricsRecorder:
    """Lightweight logger plus optional Prometheus textfile exporter."""

    def __init__(self, *, logger, textfile: str | None = None) -> None:
        self._logger = logger
        self._textfile = Path(textfile) if textfile else None
        self._ticks = 0
        self._interrupts = 0

    def record_tick(
        self,
        *,
        duration_seconds: float,
        telemetry: dict[str, Any] | None,
        pending_loops: Sequence[str] | None,
    ) -> None:
        telemetry = telemetry or {}
        cost = float(telemetry.get("llm_cost_usd", 0.0))
        last_loop = telemetry.get("last_loop", "scheduler")
        self._ticks += 1
        self._logger.info(
            "LangGraph tick",
            extra={
                "loop": last_loop,
                "duration_ms": round(duration_seconds * 1000, 2),
                "llm_cost_usd": round(cost, 4),
                "pending_loops": ",".join(pending_loops or []) if pending_loops else "",
                "ticks": self._ticks,
            },
        )
        self._write_textfile(
            duration_seconds=duration_seconds,
            telemetry=telemetry,
            pending=pending_loops or [],
        )

    def record_interrupt(self, interrupt_types: Sequence[str]) -> None:
        self._interrupts += len(interrupt_types)
        types = ", ".join(interrupt_types) or "unknown"
        self._logger.warning("LangGraph interrupt", extra={"interrupt_types": types})
        self._write_textfile()

    def _write_textfile(
        self,
        *,
        duration_seconds: float | None = None,
        telemetry: dict[str, Any] | None = None,
        pending: Sequence[str] | None = None,
    ) -> None:
        if self._textfile is None:
            return

        telemetry = telemetry or {}
        pending = pending or []
        duration = duration_seconds if duration_seconds is not None else 0.0
        last_loop = telemetry.get("last_loop", "scheduler")
        lines = [
            f"langgraph_ticks_total {self._ticks}",
            f"langgraph_interrupts_total {self._interrupts}",
            f"langgraph_last_tick_duration_seconds {duration}",
            f'langgraph_last_loop_info{{loop="{last_loop}"}} 1',
            f"langgraph_pending_loops {len(pending)}",
            f"langgraph_llm_cost_usd_total {float(telemetry.get('llm_cost_usd', 0.0))}",
        ]

        temp_path = self._textfile.with_suffix(".tmp")
        self._textfile.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temp_path.replace(self._textfile)


__all__ = ["LangGraphMetricsRecorder"]
