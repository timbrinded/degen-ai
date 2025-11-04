#!/usr/bin/env python3
"""Check what ETH spot markets are available on testnet."""

import asyncio

from hyperliquid.info import Info

from hyperliquid_agent.config import load_config
from hyperliquid_agent.market_registry import MarketRegistry


async def main():
    """Check ETH spot markets."""
    config = load_config("config.toml")
    info = Info(config.hyperliquid.base_url, skip_ws=True)
    registry = MarketRegistry(info)

    print("Hydrating market registry...")
    await registry.hydrate()

    print("\nChecking ETH markets:")
    print("=" * 60)

    # Check if ETH exists
    eth_asset = registry._assets.get("ETH")
    if eth_asset:
        print("✓ ETH found in registry")
        print(f"  Has perp: {eth_asset.perp is not None}")
        print(f"  Has spot: {len(eth_asset.spot_markets) > 0}")

        if eth_asset.perp:
            print(f"\n  Perp market: {eth_asset.perp.market_name}")

        if eth_asset.spot_markets:
            print(f"\n  Spot markets ({len(eth_asset.spot_markets)}):")
            for spot in eth_asset.spot_markets:
                print(f"    - {spot.market_name}")
    else:
        print("✗ ETH not found in registry")

    # Check UETH
    print("\n" + "=" * 60)
    print("Checking UETH markets:")
    print("=" * 60)
    ueth_asset = registry._assets.get("UETH")
    if ueth_asset:
        print("✓ UETH found in registry")
        print(f"  Has perp: {ueth_asset.perp is not None}")
        print(f"  Has spot: {len(ueth_asset.spot_markets) > 0}")

        if ueth_asset.perp:
            print(f"\n  Perp market: {ueth_asset.perp.market_name}")

        if ueth_asset.spot_markets:
            print(f"\n  Spot markets ({len(ueth_asset.spot_markets)}):")
            for spot in ueth_asset.spot_markets:
                print(f"    - {spot.market_name}")
    else:
        print("✗ UETH not found in registry")

    # List some common spot pairs
    print("\n" + "=" * 60)
    print("Sample of available spot markets:")
    print("=" * 60)
    count = 0
    for symbol, asset in registry._assets.items():
        if asset.spot_markets and count < 20:
            for spot in asset.spot_markets[:1]:  # Just show first spot market per asset
                print(f"  {symbol:10s} -> {spot.market_name}")
                count += 1
                if count >= 20:
                    break


if __name__ == "__main__":
    asyncio.run(main())
