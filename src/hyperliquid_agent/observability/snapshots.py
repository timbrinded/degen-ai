"""State snapshot serialization utilities."""

from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from hyperliquid_agent.governance.plan_card import StrategyPlanCard
from hyperliquid_agent.signals import EnhancedAccountState

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASE = PROJECT_ROOT / "state" / "snapshots"


class StateSnapshotWriter:
    """Serialize account, governance, and regime state for later replay."""

    def __init__(self, base_path: str | Path | None = None, retention: int = 20):
        self.base_path = Path(base_path) if base_path else DEFAULT_BASE
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.retention = retention

    def write(
        self,
        *,
        loop_type: str,
        account_state: EnhancedAccountState,
        plan: StrategyPlanCard | None,
        governance_meta: dict[str, Any] | None = None,
        regime_state: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Path:
        """Persist a sanitized snapshot to disk and enforce retention."""

        captured_at = datetime.now(UTC)
        payload = {
            "schema": "degen-ai.snapshot.v1",
            "loop_type": loop_type,
            "captured_at": captured_at.isoformat(),
            "account_state": _serialize(account_state),
            "plan": plan.to_dict() if plan else None,
            "governance": governance_meta or {},
            "regime": regime_state or {},
            "extra": extra or {},
        }

        filename = f"{loop_type}-{captured_at.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}.json"
        path = self.base_path / filename
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self._enforce_retention(loop_type)
        return path

    def _enforce_retention(self, loop_type: str) -> None:
        """Keep at most `retention` snapshots per loop type."""

        snapshots = sorted(
            (p for p in self.base_path.glob(f"{loop_type}-*.json") if p.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for stale_path in snapshots[self.retention :]:
            with suppress(OSError):
                stale_path.unlink()


def _serialize(value: Any) -> Any:
    """Recursively convert dataclasses and datetime objects to JSON-safe types."""

    if is_dataclass(value):
        return {k: _serialize(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    return value


__all__ = ["StateSnapshotWriter"]
