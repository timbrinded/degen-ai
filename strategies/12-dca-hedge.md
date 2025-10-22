---
title: "DCA Hedge"
id: dca-hedge
version: "1.1"
date: "2025-10-21"
markets: ["spot","perps"]
directionality: "accumulation with hedge"
risk_profile: "conservative"
leverage: "≤1x (hedge small perp)"
latency_tolerance: "very high"
llm_compatibility: "very high"
execution_style: "scheduled + small hedges"
capital_floor: 200
expected_trades_per_week: 3-10 (small)
fees_sensitivity: "low–medium"
profitability_likelihood: "medium (goal: smoother equity curve)"
hyperliquid_fit: "Spot available; use small perp overlay"
data_inputs: ["DCA schedule","funding","ATR","vol caps"]
tags: ["spot","hedged","portfolio"]
status: "draft"
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
