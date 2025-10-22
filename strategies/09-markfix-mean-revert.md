---
title: "MarkFix Mean Revert"
id: markfix-mean-revert
markets: ["perps"]
directionality: "mean-reversion"
risk_profile: "moderate"
tags: ["basis", "reversion"]

# Governance Metadata
intended_horizon: "minutes"
minimum_dwell_minutes: 30
compatible_regimes: ["range-bound", "carry-friendly"]
avoid_regimes: ["event-risk", "trending"]
invalidation_triggers:
  - "Mark-index gap widens beyond 2x entry threshold"
  - "Volatility regime flips: realized vol exceeds 80th percentile"
  - "Event tape detected: breaking news or rapid repricing begins"
  - "Time stop reached: gap persists for more than 20 minutes without convergence"
max_position_pct: 25.0
max_leverage: 2.0
expected_switching_cost_bps: 22.0
---

## Quick Read — Preconditions
- **Use when:** **Mark−Index** deviation persists for **several minutes** in quiet conditions.
- **Avoid when:** Event tape or rapid repricing.

## Concept
Fade **sustained** mark/index dislocations toward zero.

## Signals
- `gap = (mark - index)/index`; enter when `|gap| > g_enter` for `>= m` minutes and vol is low.

## Sizing & Risk
- Small sizes; stop if **gap widens** or vol regime flips.

## Execution
- **Taker** to enter once confirmation met; **maker** for adds.

## Parameters
- `g_enter=20–40 bps`, `m=3–5 min`, `exit at g_exit=5–10 bps`.

## Backtest Outline
"""
if abs(gap)>g_enter for >= m minutes and vol_low:
    enter_reversion(gap_sign)
exit when abs(gap)<g_exit or vol_spike or time_stop
"""

## Why it suits $1k + LLM latency
- Signal requires **persistence**; you don’t need to be first.
