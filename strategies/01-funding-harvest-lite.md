---
title: "Funding Harvest Lite"
id: funding-harvest-lite
version: "1.1"
date: "2025-10-21"
markets: ["perps", "spot (optional)"]
directionality: "delta-neutral preferred"
risk_profile: "conservative"
leverage: "1x–3x"
latency_tolerance: "minutes"
llm_compatibility: "high"
execution_style: "maker for perp legs where possible; taker for hedges"
capital_floor: 500
expected_trades_per_week: 3-10
fees_sensitivity: "medium"
profitability_likelihood: "medium–high (HL-specific; assume selective entries)"
hyperliquid_fit: "Good (volatile funding, low gas, cheap taker when needed)"
data_inputs:
  [
    "funding_rate (actual & predicted)",
    "index_price",
    "mark_price",
    "spot depth (if used)",
    "fees",
    "ATR or RV",
  ]
tags: ["carry", "hedged", "delta-neutral"]
status: "draft"
---

## Quick Read — Preconditions

- **Use when:** Funding is **persistently one-sided** with decent sign stability and acceptable depth for hedging (spot or correlated perp).
- **Avoid when:** Funding flips sign intraday, mark/index is unstable, or spot depth is thin.

## Concept

Harvest funding **without directional risk**:

- If funding **> 0**: **short perp**, **long spot** (same asset) **or** long a **highly correlated perp basket** as a delta hedge.
- If funding **< 0**: **long perp**, **short beta-hedge** (no short spot unless borrow exists; stick to perp hedges).

Aim for **Net APR after fees > threshold** and **cap delta drift**.

## Signals

- **Entry:** Rolling funding mean over `N` windows exceeds `min_apr` and **sign consistency** > `p%`.
- **Exit/Flip:** Funding sign change or Net APR < floor for `k` windows.

## Sizing & Risk

- Keep **effective leverage ≤ 3x** and **|delta| < 0.05 notional**.
- **Kill-switches:** mark/index divergence > `Y` bps; spot depth collapses; funding spike anomaly.

## Execution (Hyperliquid-friendly)

- **Post-only** for perp leg; hedge with **small TWAP** (spot or correlated perp).
- Re-hedge on schedule (e.g., every 30–60 min) or when **delta breach**.

## Parameters (starting points)

- `funding_ma=24 windows (1h each)`, `sign_stability=70%`, `min_apr=0.0002 per window`, `max_delta=0.05`, `rebalance_tol=15 bps`.

## Backtest Outline

"""
for each window:
est_apr = funding_apr(window) - trading_costs(window)
if est_apr > threshold and sign_stable(window):
open_or_add(hedged=True)
maintain_delta_bands()
if est_apr < exit_floor or sign_flip():
scale_out_or_close()
"""

## Monitoring

- Realized vs quoted funding, **delta drift**, fees burn, hedge slippage, and **drawdown during flips**.

## Why it suits $1k + LLM latency

- **Few decisions/hour**, tolerates minutes latency.
- Funding spikes on HL can be harvested if **selective** and **size-conservative**.
