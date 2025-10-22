---
title: "Compression Pop"
id: compression-pop
markets: ["perps", "spot"]
directionality: "directional"
risk_profile: "moderate"
tags: ["breakout", "volatility-expansion"]

# Governance Metadata
intended_horizon: "hours"
minimum_dwell_minutes: 60
compatible_regimes: ["range-bound", "trending"]
avoid_regimes: ["event-risk"]
invalidation_triggers:
  - "Price closes back inside the compression box after 3 bars"
  - "Volume surge fades: volume drops below 50% of breakout bar within 5 bars"
  - "Time stop reached: 90 minutes elapsed without follow-through"
  - "Fakeout pattern: price whipsaws through both box boundaries within 30 minutes"
max_position_pct: 40.0
max_leverage: 4.0
expected_switching_cost_bps: 18.0
---

## Quick Read — Preconditions
- **Use when:** Tight **consolidation** (low ATR, flat bands) and **volume dry‑up** pre‑expansion.
- **Avoid when:** Event risk imminent or fakeout‑prone assets.

## Concept
Trade **range compression → expansion**. Add on **retests**.

## Signals
- Close **beyond box + buffer** with **volume surge** or liquidity sweep.
- Exit if **inside back the box** after `m` bars.

## Sizing & Risk
- Stop **inside box**; trail after 1R.

## Execution
- **IOC/taker** on trigger; **maker adds** on retest limits.

## Parameters
- `box_len=20–50`, `buffer=0.15*ATR`, `trail=2*ATR`, `time_stop=90m`.

## Backtest Outline
"""
define_box()
if close>box_high+buffer and vol_surge:
    long(); add_on_retest()
    trail()
elif close<box_low-buffer and vol_surge:
    short(); add_on_retest()
    trail()
"""

## Why it suits $1k + LLM latency
- Triggers are **discrete**; you don’t need sub‑second speed.
