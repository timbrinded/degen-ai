---
title: "DCA Hedge"
id: dca-hedge
markets: ["spot", "perps"]
directionality: "accumulation"
risk_profile: "conservative"
tags: ["spot", "hedged", "portfolio"]

# Governance Metadata
intended_horizon: "days"
minimum_dwell_minutes: 1440
compatible_regimes: ["range-bound", "carry-friendly", "trending"]
avoid_regimes: []
invalidation_triggers:
  - "Spot depth unavailable: unable to source spot liquidity for scheduled buy"
  - "Funding costs erratic: funding rate volatility exceeds 3x normal"
  - "Net position flips short: hedge exceeds 50% of spot position"
  - "Accumulation target reached: portfolio allocation hits predefined ceiling"
max_position_pct: 60.0
max_leverage: 1.0
expected_switching_cost_bps: 5.0
---

## Quick Read — Preconditions
- **Use when:** You want to **accumulate spot** over time but limit drawdowns.
- **Avoid when:** You can’t source spot depth or funding costs are erratic.

## Concept
DCA small **spot buys**; during **elevated vol** or **negative drift**, add a **tiny perp hedge** (short) sized to ~20–40% beta of spot.

## Signals
- Scheduled buys; **hedge on** when ATR% > threshold or price < rolling mean by `xσ`.

## Sizing & Risk
- Keep hedge small to avoid flipping net short; unwind on recovery.

## Execution
- Batches of **maker** spot; **taker** to adjust hedge.

## Parameters
- `dca_interval=1–3 days`, `hedge_beta=0.2–0.4`, `vol_threshold=p70`, `drift_z=-1.0`.

## Backtest Outline
"""
on schedule: buy_spot_small()
if vol_high or drift_negative:
    turn_hedge_on(beta)
else:
    turn_hedge_off()
"""

## Why it suits $1k + LLM latency
- **Scheduled** and robust; hedging adjustments can be minutes late with minor impact.
