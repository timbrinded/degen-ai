---
title: "Range Sip"
id: range-sip
version: "1.1"
date: "2025-10-21"
markets: ["perps","spot"]
directionality: "mean-reversion"
risk_profile: "moderate"
leverage: "1x–3x"
latency_tolerance: "minutes"
llm_compatibility: "medium"
execution_style: "maker priority"
capital_floor: 300
expected_trades_per_week: 4-12
fees_sensitivity: "high (avoid overtrading)"
profitability_likelihood: "medium-low → medium (only in clean ranges)"
hyperliquid_fit: "OK on majors during quiet periods"
data_inputs: ["Bollinger","ATR","orderbook imbalance","realized vol slope"]
tags: ["range","stat-arb-lite"]
status: "draft"
---

## Quick Read — Preconditions
- **Use when:** Well‑defined horizontal bands and **declining vol**.
- **Avoid when:** ADX rising or news.

## Concept
Fade **band touches** to the **midline** with OB/vol confirmation.

## Signals
- Tag **2σ Bollinger** with flat slope + OB exhaustion.
- Exit at **mid** or `0.8*ATR`.

## Sizing & Risk
- **Small grid** with hard stop beyond prior wick/ATR.
- Avoid **chasing multiple fades** in an accelerating tape.

## Execution
- **Post-only** entries; **time stop** 30–90 min.

## Parameters
- `BB_len=20`, `BB_dev=2.0`, `ATR=14`, `stop=1.2*ATR`.

## Backtest Outline
"""
if band_touch and vol_slope<=0 and OB_exhaustion:
    place_maker_grid()
    target = mid_or_0p8_ATR
    stop = 1p2_ATR_beyond_extreme
"""

## Why it suits $1k + LLM latency
- Maker‑led approach reduces cost; decisions at **bar closes**, not microseconds.
