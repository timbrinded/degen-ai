"""Regime detector node that calls the live RegimeDetector."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from hyperliquid_agent.config import Config
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.state import GlobalState, StatePatch


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def regime_detector(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
) -> StatePatch:
    """Classify regime and persist state/telemetry."""

    signals = context.cache.get("regime_signals")
    if signals is None:
        return {}

    before_cost = context.regime_detector.llm_client.total_cost_usd
    classification = context.regime_detector.classify_regime(signals)
    cost_delta = context.regime_detector.llm_client.total_cost_usd - before_cost
    context.record_llm_cost("slow", max(cost_delta, 0.0))

    changed, change_reason = context.regime_detector.update_and_confirm(classification)

    metadata = {
        "loop": "slow",
        "regime": classification.regime,
        "changed": changed,
    }

    with node_trace("regime_detector", metadata=metadata) as run:
        history = [
            {
                "regime": entry.regime,
                "confidence": entry.confidence,
                "timestamp": entry.timestamp.isoformat(),
            }
            for entry in list(context.regime_detector.regime_history)
        ]

        patch: StatePatch = {
            "slow": {
                "regime_snapshot": {
                    "classification": classification.regime,
                    "confidence": classification.confidence,
                    "reasoning": classification.reasoning,
                    "updated_at": classification.timestamp.isoformat(),
                    "signals": asdict(classification.signals),
                },
                "last_detection_at": _now_iso(),
            },
            "governance": {
                "regime": {
                    "label": context.regime_detector.current_regime,
                    "confidence": classification.confidence,
                    "updated_at": classification.timestamp.isoformat(),
                    "changed": changed,
                    "change_reason": change_reason,
                    "history": history,
                }
            },
        }

        if run is not None:
            run.add_outputs(
                summarize_patch({"slow": patch["slow"], "governance": patch["governance"]})
            )
        return patch


__all__ = ["regime_detector"]
