#!/usr/bin/env python3
"""Dump raw spot metadata to see what's actually there."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from hyperliquid.info import Info

info = Info("https://api.hyperliquid-testnet.xyz", skip_ws=True)
spot_meta = info.spot_meta()

# Save to file for inspection
with open("spot_meta_dump.json", "w") as f:
    json.dump(spot_meta, f, indent=2)

print("Spot metadata dumped to spot_meta_dump.json")
print(f"Total tokens: {len(spot_meta.get('tokens', []))}")
print(f"Total markets: {len(spot_meta.get('universe', []))}")

# Check if there's an ETH token at all
tokens = spot_meta.get("tokens", [])
print("\nSearching for any token with 'ETH' (case-insensitive, exact match):")
for idx, token in enumerate(tokens):
    name = token.get("name", "")
    if name.upper() == "ETH":
        print(f"  FOUND! Token index {idx}: {name}")
        print(f"  Full token data: {token}")
