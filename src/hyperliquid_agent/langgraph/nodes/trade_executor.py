"""LangGraph node that executes (or simulates) planned actions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hyperliquid_agent.config import Config
from hyperliquid_agent.decision import TradeAction
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.state import GlobalState, StatePatch


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _to_trade_action(action: dict[str, Any]) -> TradeAction:
    return TradeAction(
        action_type=action.get("action_type", "hold"),  # type: ignore[arg-type]
        coin=str(action.get("coin", "")),
        market_type=action.get("market_type", "perp"),  # type: ignore[arg-type]
        size=float(action.get("size", 0.0)) if action.get("size") is not None else None,
        price=float(action.get("price", 0.0)) if action.get("price") is not None else None,
        reasoning=str(action.get("reasoning", "")),
        native_symbol=action.get("native_symbol"),
    )


def trade_executor(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
) -> StatePatch:
    """Execute pending actions when LangGraph is enabled; otherwise simulate."""

    execution_state = (state.get("fast") or {}).get("execution") or {}
    pending_actions = list(execution_state.get("pending_actions") or [])
    if not pending_actions:
        return {}

    metadata = {
        "loop": "fast",
        "action_count": len(pending_actions),
        "live_trading": context.langgraph_config.enabled,
    }

    results: list[dict[str, Any]] = []
    executed = 0

    with node_trace(
        "trade_executor", metadata=metadata, inputs={"count": len(pending_actions)}
    ) as run:
        if context.langgraph_config.enabled:
            for action_dict in pending_actions:
                trade_action = _to_trade_action(action_dict)
                result = context.executor.execute_action(trade_action)
                executed += 1 if result.success else 0
                results.append(
                    {
                        "coin": trade_action.coin,
                        "action_type": trade_action.action_type,
                        "size": trade_action.size,
                        "market_type": trade_action.market_type,
                        "success": result.success,
                        "order_id": result.order_id,
                        "error": result.error,
                    }
                )
        else:
            for action_dict in pending_actions:
                results.append(
                    {
                        "coin": action_dict.get("coin"),
                        "action_type": action_dict.get("action_type"),
                        "size": action_dict.get("size"),
                        "market_type": action_dict.get("market_type"),
                        "success": True,
                        "simulated": True,
                    }
                )

        summary = (
            f"{executed}/{len(pending_actions)} orders executed"
            if context.langgraph_config.enabled
            else f"{len(pending_actions)} actions simulated"
        )
        execution_patch = {
            "pending_actions": [],
            "results": results,
            "last_execution_at": _now_iso(),
            "summary": summary,
        }

        patch: StatePatch = {
            "fast": {
                "execution": execution_patch,
            },
        }

        if run is not None:
            run.add_outputs(summarize_patch({"fast": execution_patch}))
        return patch


__all__ = ["trade_executor"]
