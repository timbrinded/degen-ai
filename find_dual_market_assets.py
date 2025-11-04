#!/usr/bin/env python3
"""Find assets that have both spot and perp markets."""

import asyncio

from hyperliquid.info import Info

from hyperliquid_agent.config import load_config
from hyperliquid_agent.market_registry import MarketRegistry


async def main():
    """Find dual market assets."""
    config = load_config("config.toml")
    info = Info(config.hyperliquid.base_url, skip_ws=True)
    registry = MarketRegistry(info)

    print("Hydrating market registry...")
    await registry.hydrate()

    print("\nAssets with BOTH spot and perp markets:")
    print("=" * 70)

    dual_market_assets = []
    for symbol, asset in registry._assets.items():
        if asset.has_perp and asset.has_spot:
            dual_market_assets.append((symbol, asset))

    if dual_market_assets:
        for symbol, asset in sorted(dual_market_assets)[:20]:  # Show first 20
            perp_name = asset.perp.market_name if asset.perp else "N/A"
            spot_names = [s.market_name for s in asset.spot_markets]
            print(f"{symbol:10s} | Perp: {perp_name:10s} | Spot: {', '.join(spot_names)}")

        print(f"\nTotal: {len(dual_market_assets)} assets with both markets")
    else:
        print("No assets found with both spot and perp markets")

    print("\n" + "=" * 70)
    print("Assets with ONLY perp markets (first 10):")
    print("=" * 70)
    perp_only = [(s, a) for s, a in registry._assets.items() if a.has_perp and not a.has_spot]
    for symbol, asset in sorted(perp_only)[:10]:
        print(f"{symbol:10s} | Perp: {asset.perp.market_name if asset.perp else 'N/A'}")

    print("\n" + "=" * 70)
    print("Assets with ONLY spot markets (first 10):")
    print("=" * 70)
    spot_only = [(s, a) for s, a in registry._assets.items() if a.has_spot and not a.has_perp]
    for symbol, asset in sorted(spot_only)[:10]:
        spot_names = [s.market_name for s in asset.spot_markets]
        print(f"{symbol:10s} | Spot: {', '.join(spot_names)}")


if __name__ == "__main__":
    asyncio.run(main())
