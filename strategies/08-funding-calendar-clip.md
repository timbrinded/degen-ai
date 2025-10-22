---
title: "Funding Calendar Clip"
id: funding-calendar-clip
version: "1.1"
date: "2025-10-21"
markets: ["perps"]
directionality: "opportunistic"
risk_profile: "moderate"
leverage: "1x–3x"
latency_tolerance: "minutes"
llm_compatibility: "high"
execution_style: "scheduled + event-driven"
capital_floor: 300
expected_trades_per_week: 3-8
fees_sensitivity: "medium"
profitability_likelihood: "medium"
hyperliquid_fit: "Strong if funding behavior around windows is cyclical"
data_inputs:
  ["funding schedule/samples", "funding rate level", "oi rotation", "price"]
tags: ["funding", "timing"]
status: "draft"
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
