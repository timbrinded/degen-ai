---
title: "Session Bias"
id: session-bias
markets: ["perps", "spot"]
directionality: "directional"
risk_profile: "moderate"
tags: ["seasonality", "time-based"]

# Governance Metadata
intended_horizon: "hours"
minimum_dwell_minutes: 180
compatible_regimes: ["range-bound", "carry-friendly"]
avoid_regimes: ["event-risk", "trending"]
invalidation_triggers:
  - "Macro event or breaking news announced during session"
  - "Volatility exceeds 70th percentile threshold at session entry"
  - "Session edge degrades: rolling 30-day Sharpe drops below 0.5"
  - "Regime change detected: market transitions to strong trending behavior"
max_position_pct: 25.0
max_leverage: 2.0
expected_switching_cost_bps: 10.0
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
