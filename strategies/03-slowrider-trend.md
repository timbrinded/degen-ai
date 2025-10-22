---
title: "SlowRider Trend"
id: slowrider-trend
version: "1.1"
date: "2025-10-21"
markets: ["perps","spot"]
directionality: "directional momentum"
risk_profile: "moderate"
leverage: "1x–3x"
latency_tolerance: "hours"
llm_compatibility: "high"
execution_style: "maker adds; taker exits"
capital_floor: 300
expected_trades_per_week: 1-5
fees_sensitivity: "low–medium"
profitability_likelihood: "medium"
hyperliquid_fit: "Good (low gas, ample majors)"
data_inputs: ["EMA/DMA","Donchian","ATR","HTF bias","vol regime"]
tags: ["trend","systematic"]
status: "draft"
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
