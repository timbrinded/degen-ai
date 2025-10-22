---
title: "OI Drift Divergence"
id: oi-drift-divergence
version: "1.1"
date: "2025-10-21"
markets: ["perps"]
directionality: "directional or hedged"
risk_profile: "moderate"
leverage: "1x–3x"
latency_tolerance: "minutes-hours"
llm_compatibility: "high"
execution_style: "mixed (maker entries, taker exits)"
capital_floor: 300
expected_trades_per_week: 2-6
fees_sensitivity: "medium"
profitability_likelihood: "medium"
hyperliquid_fit: "Good where OI feed is reliable"
data_inputs: ["open_interest MAs","price trend","funding skew"]
tags: ["positioning","regime-shift"]
status: "draft"
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
