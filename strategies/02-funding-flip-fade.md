---
title: "Funding Flip Fade"
id: funding-flip-fade
version: "1.1"
date: "2025-10-21"
markets: ["perps"]
directionality: "contrarian"
risk_profile: "moderate"
leverage: "1x–4x"
latency_tolerance: "minutes"
llm_compatibility: "high"
execution_style: "limit ladder entries; taker exits"
capital_floor: 500
expected_trades_per_week: 2-8
fees_sensitivity: "medium"
profitability_likelihood: "medium (better on HL given volatile funding)"
hyperliquid_fit: "Good (funding extremes common)"
data_inputs: ["funding_rate z-score","open_interest","price trend","ATR"]
tags: ["mean-reversion","funding"]
status: "draft"
---

## Quick Read — Preconditions
- **Use when:** Funding hits **tail extremes** with simultaneous **OI expansion** (crowding).
- **Avoid when:** Fresh news breaks or strong breakout regime.

## Concept
After **funding extremes**, fade the crowded side once momentum **stalls**.

## Signals
- `z_funding > z_enter` and **OI growth** > threshold → plan **short**.
- `z_funding < -z_enter` and **OI growth** > threshold → plan **long**.
- **Exit:** z returns to band or hit **ATR-based** TP/SL.

## Sizing & Risk
- Risk `r=0.5–1.0%` per trade, **scale-in** on further extremity.
- **Time stop** (e.g., 12–24h) to avoid capital lock.

## Execution
- **Maker ladder** at edges; **taker** on exit or invalidation.

## Parameters
- `L=72 windows`, `z_enter=2.0`, `z_exit=0.5`, `oi_growth=3%/24h`, `tp=1.5 ATR`, `sl=1 ATR`.

## Backtest Outline
"""
if z_funding > z_enter and OI_up and momentum_stalls():
    enter_short(size=f(z))
elif z_funding < -z_enter and OI_up and momentum_stalls():
    enter_long(size=f(z))
manage_with_ATR_trailing()
exit on z_revert or stops
"""

## Why it suits $1k + LLM latency
- **Event-driven & slow**, decisions per **15–60 min** candle; no HFT edge required.
