"""Emergency unwind node triggered by tripwire violations."""

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


def _close_action(position) -> dict[str, Any]:
    return {
        "action_type": "close",
        "coin": position.coin,
        "market_type": position.market_type,
        "size": abs(position.size),
        "reasoning": "Tripwire emergency unwind",
    }


def emergency_unwind(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
) -> StatePatch:
    """Close all open positions when emergency unwind is required."""

    account_state = context.cache.get("fast_account_state")
    if account_state is None or not account_state.positions:
        return {}

    metadata = {
        "loop": "fast",
        "position_count": len(account_state.positions),
        "live_trading": context.langgraph_config.enabled,
    }

    unwind_actions = [
        _close_action(position) for position in account_state.positions if position.size
    ]
    results: list[dict[str, Any]] = []
    successes = 0

    with node_trace(
        "emergency_unwind", metadata=metadata, inputs={"count": len(unwind_actions)}
    ) as run:
        if context.langgraph_config.enabled:
            for action_dict in unwind_actions:
                trade_action = TradeAction(
                    action_type="close",  # type: ignore[arg-type]
                    coin=action_dict["coin"],
                    market_type=action_dict["market_type"],  # type: ignore[arg-type]
                    size=action_dict["size"],
                    reasoning=action_dict["reasoning"],
                )
                result = context.executor.execute_action(trade_action)
                successes += 1 if result.success else 0
                results.append(
                    {
                        "coin": trade_action.coin,
                        "market_type": trade_action.market_type,
                        "size": trade_action.size,
                        "success": result.success,
                        "order_id": result.order_id,
                        "error": result.error,
                    }
                )
        else:
            for action_dict in unwind_actions:
                results.append(
                    {
                        "coin": action_dict["coin"],
                        "market_type": action_dict["market_type"],
                        "size": action_dict["size"],
                        "success": True,
                        "simulated": True,
                    }
                )
                successes += 1

        summary = (
            f"{successes}/{len(unwind_actions)} positions closed"
            if context.langgraph_config.enabled
            else f"{len(unwind_actions)} positions marked for manual close"
        )

        patch: StatePatch = {
            "fast": {
                "execution": {
                    "pending_actions": [],
                    "results": results,
                    "last_execution_at": _now_iso(),
                    "summary": summary,
                },
                "tripwire": {
                    "emergency_unwind_required": False,
                },
            },
            "governance": {
                "tripwire": {
                    "emergency_unwind_required": False,
                },
            },
        }

        if run is not None:
            run.add_outputs(summarize_patch({"fast": patch["fast"]}))
        return patch


__all__ = ["emergency_unwind"]
