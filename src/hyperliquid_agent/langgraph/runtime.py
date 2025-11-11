"""Runtime utilities for executing the LangGraph orchestrator."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from langchain_core.runnables.config import RunnableConfig
from langgraph.errors import GraphInterrupt
from langgraph.types import Command, Interrupt

from hyperliquid_agent.config import Config, LangGraphConfig
from hyperliquid_agent.langgraph.graph import build_langgraph
from hyperliquid_agent.langgraph.migrations import ensure_state_version
from hyperliquid_agent.langgraph.state import GlobalState, empty_state
from hyperliquid_agent.observability.metrics import LangGraphMetricsRecorder

InterruptHandler = Callable[[GlobalState, Sequence[Interrupt]], "InterruptResolution | None"]


@dataclass(slots=True)
class InterruptResolution:
    """Resume payload produced by a human-in-the-loop interaction."""

    value: Any
    interrupt_id: str | None = None

    def as_resume_argument(self) -> Any:
        if self.interrupt_id:
            return {self.interrupt_id: self.value}
        return self.value


def default_thread_id(config: Config) -> str:
    """Derive a stable LangGraph thread id from config details."""

    prefix = config.langgraph.thread_id_prefix if config.langgraph else "degen-governed"
    suffix = config.hyperliquid.account_address[-6:]
    return f"{prefix}-{suffix}"


class LangGraphOrchestrator:
    """Controls the compiled LangGraph runtime with scheduling + HITL hooks."""

    def __init__(
        self,
        config: Config,
        *,
        logger: logging.Logger | None = None,
        thread_id: str | None = None,
        checkpoint_namespace: str | None = None,
        interrupt_handler: InterruptHandler | None = None,
    ) -> None:
        governance = config.governance
        if governance is None:
            raise ValueError("LangGraph orchestrator requires [governance] configuration")

        self._config = config
        self._logger = logger or logging.getLogger("hyperliquid_agent.langgraph.orchestrator")
        self._thread_id = thread_id or default_thread_id(config)
        self._namespace = checkpoint_namespace or (
            config.langgraph.phase_tag if config.langgraph else "langgraph"
        )
        self._interrupt_handler = interrupt_handler
        self._langgraph_cfg: LangGraphConfig = config.langgraph or LangGraphConfig()
        self._governance = governance

        self._graph, self._runtime = build_langgraph(config)
        self._state: GlobalState = ensure_state_version(empty_state())
        self._run_config: RunnableConfig = {
            "configurable": {
                "thread_id": self._thread_id,
                "checkpoint_ns": self._namespace,
            }
        }
        self._metrics = LangGraphMetricsRecorder(
            logger=self._logger,
            textfile=self._langgraph_cfg.prometheus_textfile,
        )
        self._hydrate_from_checkpoint()

    def run_forever(self) -> None:
        """Execute scheduler ticks until interrupted."""

        poll_seconds = max(1.0, float(self._langgraph_cfg.interrupt_poll_seconds))
        error_backoff = 5.0
        try:
            while True:
                wait = self._seconds_until_next_tick()
                if wait > 0:
                    time.sleep(min(wait, 5.0))

                start = time.perf_counter()
                try:
                    result_state = cast(
                        GlobalState,
                        self._graph.invoke(self._state, self._run_config),
                    )
                    self._state = ensure_state_version(result_state)
                    duration = time.perf_counter() - start
                    scheduler = self._state.get("scheduler", {}) or {}
                    pending = scheduler.get("pending_loops", [])
                    telemetry_raw = self._state.get("telemetry", {}) or {}
                    telemetry = dict(telemetry_raw)
                    pending_loops = list(pending)
                    self._metrics.record_tick(
                        duration_seconds=duration,
                        telemetry=telemetry,
                        pending_loops=pending_loops,
                    )
                except GraphInterrupt as exc:
                    interrupts = _coerce_interrupts(exc)
                    self._metrics.record_interrupt([_interrupt_label(i) for i in interrupts])
                    self._handle_interrupt(interrupts, poll_seconds)
                except KeyboardInterrupt:
                    self._logger.info("Stopping LangGraph orchestrator (Ctrl+C)")
                    break
                except Exception:
                    self._logger.exception("LangGraph execution failed; backing off")
                    time.sleep(error_backoff)
        finally:
            self._runtime.shutdown()

    def _handle_interrupt(self, interrupts: Sequence[Interrupt], poll_seconds: float) -> None:
        resolution: InterruptResolution | None = None
        if self._interrupt_handler:
            try:
                resolution = self._interrupt_handler(self._state, interrupts)
            except Exception:
                self._logger.exception("Interrupt handler raised an exception")

        if resolution is not None:
            self._resume_with(resolution)
            return

        interrupt_ids = {item.id for item in interrupts}
        self._logger.info(
            "Awaiting external approval for interrupts: %s",
            ", ".join(sorted(interrupt_ids)) or "unknown",
        )
        while True:
            time.sleep(poll_seconds)
            snapshot = self._graph.get_state(self._run_config)
            outstanding = {intr.id for intr in snapshot.interrupts}
            if interrupt_ids.isdisjoint(outstanding):
                root = (
                    snapshot.values.get("__root__") if isinstance(snapshot.values, dict) else None
                )
                if isinstance(root, dict):
                    self._state = ensure_state_version(cast(GlobalState, root))
                break

    def _resume_with(self, resolution: InterruptResolution) -> None:
        resume_payload = resolution.as_resume_argument()
        result_state = cast(
            GlobalState,
            self._graph.invoke(Command(resume=resume_payload), self._run_config),
        )
        self._state = ensure_state_version(result_state)

    def _hydrate_from_checkpoint(self) -> None:
        try:
            snapshot = self._graph.get_state(self._run_config)
        except Exception:
            return

        if snapshot and isinstance(snapshot.values, dict):
            root = snapshot.values.get("__root__")
            if isinstance(root, dict):
                self._state = ensure_state_version(cast(GlobalState, root))

    def _seconds_until_next_tick(self) -> float:
        scheduler = self._state.get("scheduler") or {}
        now = datetime.now(UTC)
        intervals = [
            self._seconds_until(
                now, scheduler.get("fast_last_run"), self._governance.fast_loop_interval_seconds
            ),
            self._seconds_until(
                now,
                scheduler.get("medium_last_run"),
                self._governance.medium_loop_interval_minutes * 60,
            ),
            self._seconds_until(
                now,
                scheduler.get("slow_last_run"),
                self._governance.slow_loop_interval_hours * 3600,
            ),
        ]
        positive = [value for value in intervals if value > 0]
        return min(positive) if positive else 0.0

    @staticmethod
    def _seconds_until(now: datetime, last_iso: Any, interval_seconds: int) -> float:
        if not isinstance(last_iso, str):
            return 0.0
        try:
            last_run = datetime.fromisoformat(last_iso)
        except ValueError:
            return 0.0
        delta = interval_seconds - (now - last_run).total_seconds()
        return max(0.0, delta)


def _coerce_interrupts(exc: GraphInterrupt) -> list[Interrupt]:
    if exc.args and isinstance(exc.args[0], Sequence):
        return [item for item in exc.args[0] if isinstance(item, Interrupt)]
    return []


def _interrupt_label(interrupt: Interrupt) -> str:
    value = interrupt.value
    if isinstance(value, dict):
        return str(value.get("type", "unknown"))
    return str(value)


__all__ = [
    "InterruptResolution",
    "LangGraphOrchestrator",
    "default_thread_id",
]
