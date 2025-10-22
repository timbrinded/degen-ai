---
title: "Range Sip"
id: range-sip
markets: ["perps", "spot"]
directionality: "mean-reversion"
risk_profile: "moderate"
tags: ["range", "stat-arb"]

# Governance Metadata
intended_horizon: "minutes"
minimum_dwell_minutes: 45
compatible_regimes: ["range-bound"]
avoid_regimes: ["trending", "event-risk"]
invalidation_triggers:
  - "ADX rises above 25 indicating trend emergence"
  - "Bollinger Band slope turns positive indicating volatility expansion"
  - "Time stop reached: 90 minutes elapsed without mean reversion"
  - "Breaking news or scheduled macro event announced"
  - "Multiple failed fades: 3 consecutive stop-outs within 2 hours"
max_position_pct: 30.0
max_leverage: 3.0
expected_switching_cost_bps: 20.0
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
