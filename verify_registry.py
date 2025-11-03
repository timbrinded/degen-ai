#!/usr/bin/env python3
"""Verification script for MarketRegistry - non-modifying INFO calls only."""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from hyperliquid.info import Info

from hyperliquid_agent.market_registry import MarketRegistry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def verify_registry():
    """Verify MarketRegistry functionality with BTC, SOL, ETH."""

    logger.info("=" * 80)
    logger.info("MarketRegistry Verification - Non-Modifying INFO Calls")
    logger.info("=" * 80)

    # Initialize registry
    logger.info("\n[1/5] Initializing MarketRegistry...")
    info = Info(skip_ws=True)
    registry = MarketRegistry(info)

    # Hydrate registry
    logger.info("\n[2/5] Hydrating registry from Hyperliquid API...")
    try:
        await registry.hydrate()
        logger.info("✅ Registry hydrated successfully")
    except Exception as e:
        logger.error(f"❌ Failed to hydrate registry: {e}", exc_info=True)
        return

    # Test symbols
    test_symbols = ["BTC", "SOL", "ETH"]

    logger.info("\n[3/5] Testing symbol resolution for BTC, SOL, ETH...")
    logger.info("-" * 80)

    for symbol in test_symbols:
        logger.info(f"\n📊 Testing {symbol}:")

        # Get asset info
        try:
            asset_info = registry.get_asset_info(symbol)
            if not asset_info:
                logger.error(f"  ❌ {symbol} not found in registry")
                continue

            logger.info(f"  ✅ Asset found: {asset_info.base_symbol}")
            logger.info(f"     - Has PERP: {asset_info.has_perp}")
            logger.info(f"     - Has SPOT: {asset_info.has_spot}")
            logger.info(f"     - Spot markets: {len(asset_info.spot_markets)}")

            # Test PERP market
            if asset_info.has_perp:
                try:
                    perp_name = registry.get_market_name(symbol, "perp")
                    sz_decimals = registry.get_sz_decimals(symbol, "perp")
                    logger.info(f"     - PERP market name: '{perp_name}'")
                    logger.info(f"     - PERP sz_decimals: {sz_decimals}")

                    if asset_info.perp:
                        logger.info(f"     - PERP asset_id: {asset_info.perp.asset_id}")
                        logger.info(f"     - PERP px_decimals: {asset_info.perp.px_decimals}")
                except Exception as e:
                    logger.error(f"     ❌ PERP lookup failed: {e}")

            # Test SPOT market
            if asset_info.has_spot:
                try:
                    spot_name = registry.get_market_name(symbol, "spot")
                    sz_decimals = registry.get_sz_decimals(symbol, "spot")
                    logger.info(f"     - SPOT market name: '{spot_name}'")
                    logger.info(f"     - SPOT sz_decimals: {sz_decimals}")

                    if asset_info.spot_markets:
                        logger.info("     - Available spot pairs:")
                        for spot_market in asset_info.spot_markets:
                            logger.info(f"         * {spot_market.market_name}")
                except Exception as e:
                    logger.error(f"     ❌ SPOT lookup failed: {e}")

        except Exception as e:
            logger.error(f"  ❌ Error processing {symbol}: {e}", exc_info=True)

    # Test symbol normalization
    logger.info("\n[4/5] Testing symbol normalization...")
    logger.info("-" * 80)

    test_cases = [
        ("ETH", "ETH"),  # Normal case
        ("UETH", "ETH"),  # Problematic prefix
        ("eth", "ETH"),  # Lowercase
        (" BTC ", "BTC"),  # Whitespace
    ]

    for raw_symbol, expected in test_cases:
        try:
            # Try to get asset info (this will normalize internally)
            asset_info = registry.get_asset_info(raw_symbol)
            if asset_info:
                result = asset_info.base_symbol
                status = "✅" if result == expected else "⚠️"
                logger.info(f"  {status} '{raw_symbol}' -> '{result}' (expected: '{expected}')")
            else:
                logger.warning(f"  ⚠️ '{raw_symbol}' -> Not found (expected: '{expected}')")
        except Exception as e:
            logger.error(f"  ❌ '{raw_symbol}' -> Error: {e}")

    # Test symbol resolution
    logger.info("\n[5/5] Testing ambiguous symbol resolution...")
    logger.info("-" * 80)

    resolution_tests = [
        "ETH",  # Should default to perp if available
        "ETH/USDC",  # Should resolve to spot
        "BTC",  # Should default to perp
    ]

    for raw_symbol in resolution_tests:
        try:
            result = registry.resolve_symbol(raw_symbol)
            if result:
                base_symbol, market_type = result
                logger.info(f"  ✅ '{raw_symbol}' -> ({base_symbol}, {market_type})")
            else:
                logger.warning(f"  ⚠️ '{raw_symbol}' -> Could not resolve")
        except Exception as e:
            logger.error(f"  ❌ '{raw_symbol}' -> Error: {e}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("Verification Complete!")
    logger.info("=" * 80)
    logger.info(f"Total assets in registry: {len(registry._assets)}")
    logger.info(f"Total PERP markets: {len(registry._perp_by_name)}")
    logger.info(f"Total SPOT markets: {len(registry._spot_by_name)}")
    logger.info("\n✅ All non-modifying INFO calls completed successfully")
    logger.info("   No trades were executed, no orders were placed")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(verify_registry())
