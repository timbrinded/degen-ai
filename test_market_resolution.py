#!/usr/bin/env python3
"""Test market name resolution for various coins."""

import asyncio

from hyperliquid.info import Info

from hyperliquid_agent.config import load_config
from hyperliquid_agent.market_registry import MarketRegistry


async def main():
    """Test market resolution."""
    config = load_config("config.toml")
    info = Info(config.hyperliquid.base_url, skip_ws=True)
    registry = MarketRegistry(info)

    print("Hydrating market registry...")
    await registry.hydrate()

    test_cases = [
        ("ETH", "perp"),
        ("ETH", "spot"),
        ("UETH", "spot"),
        ("UETH", "perp"),
        ("BTC", "perp"),
        ("BTC", "spot"),
        ("PURR", "spot"),
        ("PURR", "perp"),
    ]

    print("\nTesting market name resolution:")
    print("=" * 70)

    for coin, market_type in test_cases:
        try:
            market_name = registry.get_market_name(coin, market_type)
            print(f"✓ {coin:10s} {market_type:5s} -> {market_name}")
        except Exception as e:
            print(f"✗ {coin:10s} {market_type:5s} -> ERROR: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
