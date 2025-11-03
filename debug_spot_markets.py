#!/usr/bin/env python3
"""Debug script to understand Hyperliquid spot market structure."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from hyperliquid.info import Info


async def debug_spot_structure():
    """Investigate the actual structure of spot_meta."""

    print("=" * 80)
    print("Debugging Hyperliquid Spot Market Structure")
    print("=" * 80)

    info = Info(skip_ws=True)

    # Get spot metadata
    print("\n[1] Fetching spot_meta()...")
    spot_meta = await asyncio.to_thread(info.spot_meta)

    print(f"\nKeys in spot_meta: {list(spot_meta.keys())}")

    # Examine tokens
    print("\n[2] Tokens array (first 10):")
    tokens = spot_meta.get("tokens", [])
    print(f"Total tokens: {len(tokens)}")
    for i, token in enumerate(tokens[:10]):
        print(f"  Token[{i}]: {json.dumps(token, indent=4)}")

    # Examine universe
    print("\n[3] Universe array (first 5):")
    universe = spot_meta.get("universe", [])
    print(f"Total spot markets: {len(universe)}")
    for i, market in enumerate(universe[:5]):
        print(f"\n  Market[{i}]:")
        print(f"    name: {market.get('name')}")
        print(f"    tokens: {market.get('tokens')}")

        # Decode the token pair
        if "tokens" in market and len(market["tokens"]) == 2:
            base_idx, quote_idx = market["tokens"]
            if base_idx < len(tokens) and quote_idx < len(tokens):
                base_token = tokens[base_idx]
                quote_token = tokens[quote_idx]
                print(
                    f"    base_token[{base_idx}]: {base_token.get('name')} (full: {json.dumps(base_token)})"
                )
                print(
                    f"    quote_token[{quote_idx}]: {quote_token.get('name')} (full: {json.dumps(quote_token)})"
                )

    # Search for ETH, BTC, SOL in spot markets
    print("\n[4] Searching for ETH, BTC, SOL in spot markets...")
    for target in ["ETH", "BTC", "SOL"]:
        print(f"\n  Looking for {target}:")
        found = []

        for market in universe:
            market_name = market.get("name", "")

            # Check if target is in market name
            if target in market_name.upper():
                token_pair = market.get("tokens", [])
                if len(token_pair) == 2:
                    base_idx, quote_idx = token_pair
                    if base_idx < len(tokens) and quote_idx < len(tokens):
                        base_name = tokens[base_idx].get("name", "")
                        quote_name = tokens[quote_idx].get("name", "")
                        found.append(
                            {
                                "market_name": market_name,
                                "base": base_name,
                                "quote": quote_name,
                                "base_idx": base_idx,
                                "quote_idx": quote_idx,
                            }
                        )

        if found:
            print(f"    ✅ Found {len(found)} markets:")
            for m in found:
                print(
                    f"       - {m['market_name']}: {m['base']}/{m['quote']} (indices: {m['base_idx']}, {m['quote_idx']})"
                )
        else:
            print("    ❌ No markets found")

    # Check name_to_coin mapping
    print("\n[5] Checking Info.name_to_coin for spot markets...")
    print(f"  'ETH' in name_to_coin: {'ETH' in info.name_to_coin}")
    print(f"  'ETH/USDC' in name_to_coin: {'ETH/USDC' in info.name_to_coin}")

    # Sample some entries from name_to_coin
    print("\n  Sample name_to_coin entries (first 10):")
    for _, (name, coin_id) in enumerate(list(info.name_to_coin.items())[:10]):
        print(f"    '{name}' -> {coin_id}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(debug_spot_structure())
