---
title: "Funding Flip Fade"
id: funding-flip-fade
markets: ["perps"]
directionality: "contrarian"
risk_profile: "moderate"
tags: ["mean-reversion", "funding"]

# Governance Metadata
intended_horizon: "hours"
minimum_dwell_minutes: 90
compatible_regimes: ["range-bound", "carry-friendly"]
avoid_regimes: ["trending", "event-risk"]
invalidation_triggers:
  - "Funding z-score returns to neutral band (abs(z) < 0.5) for 4 consecutive windows"
  - "Fresh breaking news or major market event announced"
  - "Strong breakout confirmed with volume surge and ADX > 30"
  - "Time stop reached: position held for more than 24 hours without mean reversion"
max_position_pct: 35.0
max_leverage: 4.0
expected_switching_cost_bps: 12.0
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
