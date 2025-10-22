---
title: "Unlock Watch"
id: unlock-watch
markets: ["perps", "spot"]
directionality: "event-driven"
risk_profile: "moderate"
tags: ["events", "risk-on-off"]

# Governance Metadata
intended_horizon: "hours"
minimum_dwell_minutes: 180
compatible_regimes: ["event-risk"]
avoid_regimes: []
invalidation_triggers:
  - "Liquidity collapses: bid-ask spread exceeds 100 bps around event"
  - "Max loss per event reached: position hits predefined loss threshold"
  - "Event outcome differs from historical pattern: no expected reaction within 2 hours"
  - "Surprise announcement: unexpected protocol change or delay announced"
max_position_pct: 20.0
max_leverage: 2.0
expected_switching_cost_bps: 30.0
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
