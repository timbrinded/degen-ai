#!/usr/bin/env python3
"""Quick check for ETH in spot markets."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from hyperliquid.info import Info

info = Info("https://api.hyperliquid-testnet.xyz", skip_ws=True)
spot_meta = info.spot_meta()

tokens = spot_meta.get("tokens", [])
universe = spot_meta.get("universe", [])

# Find ETH token
print("Looking for ETH token...")
for idx, token in enumerate(tokens):
    name = token.get("name", "")
    if "ETH" in name.upper() and len(name) <= 4:
        print(f"  Token {idx}: {name}")

# Find ETH markets
print("\nLooking for ETH spot markets...")
for market in universe:
    market_name = market.get("name", "")
    if "ETH" in market_name.upper():
        token_pair = market.get("tokens", [])
        if len(token_pair) == 2:
            base_idx, quote_idx = token_pair
            base_name = tokens[base_idx].get("name", "?") if base_idx < len(tokens) else "?"
            quote_name = tokens[quote_idx].get("name", "?") if quote_idx < len(tokens) else "?"
            print(f"  {market_name}: {base_name}/{quote_name} (indices: {base_idx}, {quote_idx})")

# Also check for HYPE since that's what the screenshot shows
print("\nLooking for HYPE spot markets...")
for market in universe:
    market_name = market.get("name", "")
    if "HYPE" in market_name.upper():
        token_pair = market.get("tokens", [])
        if len(token_pair) == 2:
            base_idx, quote_idx = token_pair
            base_name = tokens[base_idx].get("name", "?") if base_idx < len(tokens) else "?"
            quote_name = tokens[quote_idx].get("name", "?") if quote_idx < len(tokens) else "?"
            print(f"  {market_name}: {base_name}/{quote_name} (indices: {base_idx}, {quote_idx})")
