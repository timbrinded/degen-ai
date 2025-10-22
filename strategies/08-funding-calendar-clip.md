---
title: "Funding Calendar Clip"
id: funding-calendar-clip
markets: ["perps"]
directionality: "opportunistic"
risk_profile: "moderate"
tags: ["funding", "timing"]

# Governance Metadata
intended_horizon: "minutes"
minimum_dwell_minutes: 60
compatible_regimes: ["carry-friendly", "range-bound"]
avoid_regimes: ["event-risk"]
invalidation_triggers:
  - "Funding rate flips sign unexpectedly during the window"
  - "OI rotation pattern breaks: OI increases instead of rolling off"
  - "Time stop reached: post-window period ends without expected behavior"
  - "Price volatility spike: realized vol exceeds 2x normal during window"
max_position_pct: 30.0
max_leverage: 3.0
expected_switching_cost_bps: 16.0
---

## Quick Read — Preconditions

- **Use when:** Funding **consistently one-sided**, and traders **de‑risk** into/after the accrual windows.
- **Avoid when:** Funding is flat/noisy.

## Concept

Time **pre‑/post‑funding** behavior:

- Short into **positive funding** windows; cover post.
- Long into **negative funding** windows; de‑risk post.

## Signals

- `funding > threshold` + **OI roll-off** near window start.

## Sizing & Risk

- Small, **time-boxed** trades; hard **time stops**.

## Execution

- **Maker entries** if time; **taker exits** around window.

## Parameters

- `window_pre=30–90m`, `window_post=15–45m`, `funding_q=70%`.

## Backtest Outline

"""
if funding>thr and pre_window and OI_rolloff:
short_until(post_window_end)
elif funding<-thr and pre_window and OI_rolloff:
long_until(post_window_end)
"""

## Why it suits $1k + LLM latency

- **Clock-driven**, minutes‑scale tolerant, and focused on a known cadence.
