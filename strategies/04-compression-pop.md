---
title: "Compression Pop"
id: compression-pop
version: "1.1"
date: "2025-10-21"
markets: ["perps","spot"]
directionality: "directional breakout"
risk_profile: "moderate"
leverage: "1x–4x"
latency_tolerance: "minutes"
llm_compatibility: "medium-high"
execution_style: "taker on trigger; maker for retest adds"
capital_floor: 300
expected_trades_per_week: 2-6
fees_sensitivity: "medium"
profitability_likelihood: "medium"
hyperliquid_fit: "Good on majors; verify noise on small caps"
data_inputs: ["range width","ATR","volume surge","OB sweep"]
tags: ["breakout","volatility expansion"]
status: "draft"
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
