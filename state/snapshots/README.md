# State Snapshot Baseline

Snapshots are JSON documents produced during each governed-loop iteration (fast/medium/slow).
They capture the minimum state required to replay a tick inside LangGraph.

## File Layout

```
state/snapshots/
  fast-<timestamp>-<id>.json
  medium-<timestamp>-<id>.json
  slow-<timestamp>-<id>.json
```

Files follow the schema identifier `degen-ai.snapshot.v1` and include:

| Field | Description |
| --- | --- |
| `schema` | Version tag for downstream validators. |
| `loop_type` | `fast`, `medium`, or `slow`. |
| `captured_at` | UTC timestamp when the snapshot was created. |
| `account_state` | Serialized `EnhancedAccountState` (positions, balances, signals, price map). |
| `plan` | Active `StrategyPlanCard` serialized via `to_dict()`. `null` when no plan is active. |
| `governance` | Lightweight metadata: active plan id/status, rebalance progress, active tripwires, last change timestamp. |
| `regime` | Current regime label, regime-history length, top 3 macro events with ISO datetimes. |
| `extra` | Tick counter and future extensions. |

All dataclass instances are expanded to primitive types, with datetimes converted to ISO strings and decimals coerced to floats. No private keys or credential material are included in snapshots by design.

## Usage

1. Load the JSON document.
2. Reconstruct `EnhancedAccountState`/`StrategyPlanCard` via the provided `from_dict` helpers if needed.
3. Feed the payload into LangGraph dry-runs or regression tests.

Retention defaults to the latest 20 snapshots per loop (configurable in `StateSnapshotWriter`). Remove or archive files freely—they are regenerated at runtime.
