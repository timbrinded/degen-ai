---
title: "MarkFix Mean Revert"
id: markfix-mean-revert
version: "1.1"
date: "2025-10-21"
markets: ["perps"]
directionality: "reversion"
risk_profile: "moderate"
leverage: "1x–2x"
latency_tolerance: "minutes"
llm_compatibility: "high"
execution_style: "taker on confirm; maker for partial adds"
capital_floor: 300
expected_trades_per_week: 2-6
fees_sensitivity: "medium"
profitability_likelihood: "medium"
hyperliquid_fit: "Good if mark-index gaps persist for minutes"
data_inputs: ["mark minus index","ATR","vol regime","spread"]
tags: ["basis","reversion"]
status: "draft"
---

## Quick Read — Preconditions
- **Use when:** **Mark−Index** deviation persists for **several minutes** in quiet conditions.
- **Avoid when:** Event tape or rapid repricing.

## Concept
Fade **sustained** mark/index dislocations toward zero.

## Signals
- `gap = (mark - index)/index`; enter when `|gap| > g_enter` for `>= m` minutes and vol is low.

## Sizing & Risk
- Small sizes; stop if **gap widens** or vol regime flips.

## Execution
- **Taker** to enter once confirmation met; **maker** for adds.

## Parameters
- `g_enter=20–40 bps`, `m=3–5 min`, `exit at g_exit=5–10 bps`.

## Backtest Outline
"""
if abs(gap)>g_enter for >= m minutes and vol_low:
    enter_reversion(gap_sign)
exit when abs(gap)<g_exit or vol_spike or time_stop
"""

## Why it suits $1k + LLM latency
- Signal requires **persistence**; you don’t need to be first.
