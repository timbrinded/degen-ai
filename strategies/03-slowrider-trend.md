---
title: "SlowRider Trend"
id: slowrider-trend
markets: ["perps", "spot"]
directionality: "directional"
risk_profile: "moderate"
tags: ["trend", "systematic"]

# Governance Metadata
intended_horizon: "days"
minimum_dwell_minutes: 240
compatible_regimes: ["trending"]
avoid_regimes: ["range-bound", "event-risk"]
invalidation_triggers:
  - "EMA crossover reversal: fast EMA crosses below slow EMA for longs (or above for shorts)"
  - "Trailing stop hit: price moves 3*ATR against position"
  - "Market enters choppy regime: ADX drops below 20 for 3 consecutive periods"
  - "Volatility collapse: ATR percentile drops below 30th percentile"
max_position_pct: 50.0
max_leverage: 3.0
expected_switching_cost_bps: 8.0
---

## Quick Read — Preconditions
- **Use when:** Clear **HTF trend** and rising volatility.
- **Avoid when:** Choppy, mean‑reverting regimes.

## Concept
Classic **time‑series momentum** with **ATR risk** and **trailing stops**.

## Signals
- `EMA21 > EMA55` and price > weekly VWAP → **long** bias; reverse for shorts.
- Donchian breakout confirmation (20 bars).

## Sizing & Risk
- Position size = `risk_per_trade / ATR`.
- **Trail stop** at `3 * ATR`; **portfolio heat** cap.

## Execution
- **Maker adds** on pullbacks; **taker exit** on stop/reversal.

## Parameters
- `EMA_fast=21`, `EMA_slow=55`, `Donchian=20`, `ATR=14`, `trail=3*ATR`.

## Backtest Outline
"""
if HTF_up and EMA_fast>EMA_slow and ATR%>vol_min:
    long; trail_stop(3*ATR)
elif HTF_down and EMA_fast<EMA_slow:
    short; trail_stop(3*ATR)
"""

## Why it suits $1k + LLM latency
- **Low decision frequency**; stop/scale logic tolerates minute‑scale response.
