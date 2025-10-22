---
title: "Pairs Beta Sync"
id: pairs-beta-sync
markets: ["perps", "spot"]
directionality: "relative-value"
risk_profile: "moderate"
tags: ["pairs", "stat-arb", "hedged"]

# Governance Metadata
intended_horizon: "hours"
minimum_dwell_minutes: 120
compatible_regimes: ["range-bound", "carry-friendly"]
avoid_regimes: ["event-risk"]
invalidation_triggers:
  - "Cointegration relationship breaks: rolling beta changes by more than 30%"
  - "Protocol news or token listing announced affecting one leg"
  - "Time stop reached: spread half-life elapsed without mean reversion"
  - "Spread volatility spike: spread vol exceeds 2x historical average"
  - "Leg synchronization fails: unable to execute both legs within 5 minutes"
max_position_pct: 40.0
max_leverage: 2.0
expected_switching_cost_bps: 25.0
---

## Quick Read — Preconditions
- **Use when:** Two assets show a **stable relationship** (beta/cointegration) and temporary dislocations.
- **Avoid when:** Protocol news or listings break relationships.

## Concept
Trade **spread**: long undervalued leg, short overvalued leg to mean reversion, **beta‑hedged** to near‑zero delta.

## Signals
- Residual z‑score `>|z_enter|`; exit near 0.

## Sizing & Risk
- Size by **spread vol**; **time stop** at spread half‑life.

## Execution
- Staggered **maker entries**; synchronize legs within **seconds‑minutes**.

## Parameters
- `lookback=300 bars`, `z_enter=2.0`, `z_exit=0.5`.

## Backtest Outline
"""
res = y - beta*x
if z(res)>z_enter: short y, long x (beta-adjusted)
if z(res)<-z_enter: long y, short x
exit when |z|<z_exit or half_life elapsed
"""

## Why it suits $1k + LLM latency
- **Delta‑light**, few trades; latency tolerant (minutes).
