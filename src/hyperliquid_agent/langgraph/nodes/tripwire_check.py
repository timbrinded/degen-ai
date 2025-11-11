"""LangGraph node that runs live tripwire checks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hyperliquid_agent.config import Config
from hyperliquid_agent.governance.tripwire import TripwireAction
from hyperliquid_agent.langgraph.context import LangGraphRuntimeContext
from hyperliquid_agent.langgraph.instrumentation import node_trace, summarize_patch
from hyperliquid_agent.langgraph.state import FAST_LOOP, GlobalState, StatePatch


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _format_events(events: list) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for event in events:
        formatted.append(
            {
                "severity": event.severity,
                "category": event.category,
                "trigger": event.trigger,
                "action": event.action.value,
                "timestamp": event.timestamp.isoformat(),
                "details": event.details,
            }
        )
    return formatted


def tripwire_check(
    state: GlobalState,
    config: Config,
    *,
    context: LangGraphRuntimeContext,
) -> StatePatch:
    """Run TripwireService checks using the latest fast-loop account state."""

    account_state = context.cache.get("fast_account_state")
    if account_state is None:
        return {}

    plan = context.governor.active_plan
    events = context.tripwire.check_all_tripwires(account_state, plan)
    formatted_events = _format_events(events)
    emergency = any(
        event.action in {TripwireAction.CUT_SIZE_TO_FLOOR, TripwireAction.INVALIDATE_PLAN}
        for event in events
    )

    metadata = {
        "loop": FAST_LOOP,
        "plan_id": plan.plan_id if plan else None,
        "violation_count": len(events),
        "langgraph_phase": context.langgraph_config.phase_tag,
    }

    with node_trace("tripwire_check", metadata=metadata, inputs={"count": len(events)}) as run:
        tripwire_state = {
            "violations": formatted_events,
            "last_run": _now_iso(),
            "emergency_unwind_required": emergency,
        }

        governance_tripwire = {
            **tripwire_state,
        }

        interrupts = list(state.get("governance", {}).get("interrupts", []))
        if emergency:
            interrupts.append(
                {
                    "type": "tripwire_emergency",
                    "raised_at": tripwire_state["last_run"],
                    "details": formatted_events,
                }
            )

        patch: StatePatch = {
            "fast": {
                "tripwire": tripwire_state,
            },
            "governance": {
                "tripwire": governance_tripwire,
                "interrupts": interrupts,
            },
        }

        if run is not None:
            run.add_outputs(summarize_patch(patch))
        return patch


__all__ = ["tripwire_check"]
