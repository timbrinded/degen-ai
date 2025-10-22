---
title: "Unlock Watch"
id: unlock-watch
version: "1.1"
date: "2025-10-21"
markets: ["perps","spot"]
directionality: "event-driven"
risk_profile: "moderate"
leverage: "1x–2x"
latency_tolerance: "high"
llm_compatibility: "high"
execution_style: "taker on trigger"
capital_floor: 300
expected_trades_per_week: 0-3 (sporadic)
fees_sensitivity: "low"
profitability_likelihood: "medium (if disciplined)"
hyperliquid_fit: "Works on tokens with known unlocks/airdrops"
data_inputs: ["token unlock calendar","ATR","HTF levels","funding"]
tags: ["events","risk-on/off"]
status: "draft"
---

## Quick Read — Preconditions
- **Use when:** A token has a **scheduled unlock** with historical reaction patterns.
- **Avoid when:** Liquidity too thin around event.

## Concept
Trade **pre‑unlock drift** (fade if overextended into resistance), or **post‑surprise momentum** if level breaks with volume.

## Signals
- Pre‑event **overextension** into HTF level → fade small.
- Post‑event **break + surge** → chase with tight leash.

## Sizing & Risk
- Hard **max loss per event**; **wider initial stops**.

## Execution
- Pre‑place **stop entries**; cancel if no trigger.

## Parameters
- `pre_drift_thr=1.0–1.5 ATR`, `surprise_vol_q=80%`, `rr=1.5`.

## Backtest Outline
"""
for each scheduled_unlock:
    if pre_drift>thr and into_resistance: small_fade()
    if post_break and vol_surge: momentum_follow_with_tight_stop()
"""

## Why it suits $1k + LLM latency
- Few events; playbook‑driven; no microsecond reactions.
