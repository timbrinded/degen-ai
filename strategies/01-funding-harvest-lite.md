---
title: "Funding Harvest Lite"
id: funding-harvest-lite
markets: ["perps", "spot"]
directionality: "delta-neutral"
risk_profile: "conservative"
tags: ["carry", "hedged", "delta-neutral"]

# Governance Metadata
intended_horizon: "hours"
minimum_dwell_minutes: 120
compatible_regimes: ["carry-friendly", "range-bound"]
avoid_regimes: ["event-risk", "trending"]
invalidation_triggers:
  - "Funding rate flips sign and remains negative for 3 consecutive windows"
  - "Mark-index divergence exceeds 50 bps for more than 15 minutes"
  - "Spot depth collapses below 50% of 24h average"
  - "Delta drift exceeds 0.08 notional despite rehedging attempts"
max_position_pct: 40.0
max_leverage: 3.0
expected_switching_cost_bps: 15.0
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
