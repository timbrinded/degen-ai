---
title: "OI Drift Divergence"
id: oi-drift-divergence
markets: ["perps"]
directionality: "directional"
risk_profile: "moderate"
tags: ["positioning", "regime-shift"]

# Governance Metadata
intended_horizon: "hours"
minimum_dwell_minutes: 90
compatible_regimes: ["trending", "range-bound"]
avoid_regimes: ["event-risk"]
invalidation_triggers:
  - "OI trend reverses and aligns with price direction for 5 consecutive bars"
  - "OI data feed becomes unreliable or stale for more than 10 minutes"
  - "ATR stop hit: price moves 1.5*ATR against position"
  - "Divergence resolves: price breaks structure in direction of OI trend"
max_position_pct: 35.0
max_leverage: 3.0
expected_switching_cost_bps: 14.0
---

## Quick Read — Preconditions
- **Use when:** Price trend **disagrees** with OI trend (distribution or absorption).
- **Avoid when:** OI feed is noisy or missing.

## Concept
Exploit **price–OI divergence**:
- **Rally + falling OI** → distribution → fade/hedge.
- **Dump + rising OI** → shorts piling → squeeze setup.

## Signals
- `OI_MA_fast` crosses `OI_MA_slow` against price direction; funding skew agrees.

## Sizing & Risk
- Start **small/hedged**; add on break of structure.
- `ATR_stop=1.5`.

## Execution
- **Maker** where possible; **taker** on exits.

## Parameters
- `OI_MA_fast=8`, `OI_MA_slow=34`, `confirm_bars=3`.

## Backtest Outline
"""
if price_up and OI_trend_down and confirm_bars_passed:
    open_small_short_or_hedge()
elif price_down and OI_trend_up:
    open_small_long_or_hedge()
manage_with_ATR_stops()
"""

## Why it suits $1k + LLM latency
- Decisions are **slow**; emphasis on positioning rather than tick games.
