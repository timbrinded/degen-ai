---
title: "Pairs Beta Sync"
id: pairs-beta-sync
version: "1.1"
date: "2025-10-21"
markets: ["perps","spot (optional)"]
directionality: "relative-value"
risk_profile: "moderate"
leverage: "1x–2x"
latency_tolerance: "minutes-hours"
llm_compatibility: "high"
execution_style: "maker legs where possible"
capital_floor: 800
expected_trades_per_week: 1-4
fees_sensitivity: "medium"
profitability_likelihood: "medium (liquidity-dependent)"
hyperliquid_fit: "Better with sector-mates and ETH beta"
data_inputs: ["prices","rolling beta","cointegration test","spread volatility"]
tags: ["pairs","stat-arb","hedged"]
status: "draft"
---

## Quick Read — Preconditions
- **Use when:** Two assets show a **stable relationship** (beta/cointegration) and temporary dislocations.
- **Avoid when:** Protocol news or listings break relationships.

## Concept
Trade **spread**: long undervalued leg, short overvalued leg to mean reversion, **beta‑hedged** to near‑zero delta.

## Signals
- Residual z‑score `>|z_enter|`; exit near 0.

## Sizing & Risk
- Size by **spread vol**; **time stop** at spread half‑life.

## Execution
- Staggered **maker entries**; synchronize legs within **seconds‑minutes**.

## Parameters
- `lookback=300 bars`, `z_enter=2.0`, `z_exit=0.5`.

## Backtest Outline
"""
res = y - beta*x
if z(res)>z_enter: short y, long x (beta-adjusted)
if z(res)<-z_enter: long y, short x
exit when |z|<z_exit or half_life elapsed
"""

## Why it suits $1k + LLM latency
- **Delta‑light**, few trades; latency tolerant (minutes).
