---
title: "Session Bias"
id: session-bias
version: "1.1"
date: "2025-10-21"
markets: ["perps","spot"]
directionality: "time-of-day directional"
risk_profile: "moderate"
leverage: "1x–2x"
latency_tolerance: "high"
llm_compatibility: "very high"
execution_style: "scheduled"
capital_floor: 200
expected_trades_per_week: 5-10
fees_sensitivity: "low–medium"
profitability_likelihood: "medium-low → medium (only if asset shows seasonal edge)"
hyperliquid_fit: "Simple to automate; skip on event days"
data_inputs: ["intraday return profile","funding","volatility","macro/event calendar"]
tags: ["seasonality","time-based"]
status: "draft"
---

## Quick Read — Preconditions
- **Use when:** An asset shows **repeatable session drift** (analyzed monthly).
- **Avoid when:** Macro/event weeks or regime changes.

## Concept
Go with historically **positive sessions**; be flat/hedged otherwise.

## Signals
- Choose sessions with **positive mean & Sharpe**; overlay **funding filter**.

## Sizing & Risk
- Flat at **session end**; **volatility caps** on entry.

## Execution
- Cron‑like scheduler; **skip on event days**.

## Parameters
- `session_windows`, `skip_events=true`, `vol_cap=70th pct`.

## Backtest Outline
"""
for session in sessions:
    if edge>threshold and not event_day:
        enter_at_open(); exit_at_close()
"""

## Why it suits $1k + LLM latency
- **Fully scheduled**, minimal interaction; easy to risk‑cap.
