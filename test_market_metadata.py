#!/usr/bin/env python3
"""Diagnostic script to test market metadata retrieval from Hyperliquid testnet.

This script connects to the Hyperliquid testnet and dumps all available spot and
perpetual market metadata. It specifically checks for ETH availability on both
market types to diagnose trading issues.

Usage:
    python test_market_metadata.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from hyperliquid.info import Info

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Main diagnostic function."""
    logger.info("=" * 80)
    logger.info("Hyperliquid Market Metadata Diagnostic")
    logger.info("=" * 80)

    # Initialize Info API client for testnet
    testnet_url = "https://api.hyperliquid-testnet.xyz"
    info = Info(testnet_url, skip_ws=True)

    logger.info(f"\nConnecting to: {testnet_url}")
    logger.info("-" * 80)

    # Fetch perpetual market metadata
    logger.info("\n[1] FETCHING PERPETUAL MARKET METADATA")
    logger.info("-" * 80)

    try:
        perp_meta = await asyncio.to_thread(info.meta)
        perp_universe = perp_meta.get("universe", [])

        logger.info("✓ Successfully fetched perpetual metadata")
        logger.info(f"  Total perpetual markets: {len(perp_universe)}")

        # Log all perp markets
        logger.info("\n  Available Perpetual Markets:")
        eth_found_perp = False

        for idx, asset in enumerate(perp_universe, 1):
            name = asset.get("name", "UNKNOWN")
            asset_id = asset.get("assetId", "N/A")
            sz_decimals = asset.get("szDecimals", "N/A")

            logger.info(f"    {idx:3d}. {name:15s} (ID: {asset_id:4s}, sz_decimals: {sz_decimals})")

            if name.upper() == "ETH":
                eth_found_perp = True
                logger.info("         ✓ ETH FOUND on perpetual market")
                logger.info(f"         Full metadata: {asset}")

        if not eth_found_perp:
            logger.warning("  ⚠ ETH NOT FOUND on perpetual markets")

    except Exception as e:
        logger.error(f"✗ Failed to fetch perpetual metadata: {e}", exc_info=True)
        return 1

    # Fetch spot market metadata
    logger.info("\n[2] FETCHING SPOT MARKET METADATA")
    logger.info("-" * 80)

    try:
        spot_meta = await asyncio.to_thread(info.spot_meta)
        spot_universe = spot_meta.get("universe", [])
        tokens = spot_meta.get("tokens", [])

        logger.info("✓ Successfully fetched spot metadata")
        logger.info(f"  Total spot markets: {len(spot_universe)}")
        logger.info(f"  Total tokens: {len(tokens)}")

        # Log token list
        logger.info("\n  Available Tokens:")
        for idx, token in enumerate(tokens):
            token_name = token.get("name", "UNKNOWN")
            token_index = token.get("index", idx)
            logger.info(f"    {token_index:3d}. {token_name}")

        # Log all spot markets
        logger.info("\n  Available Spot Markets:")
        eth_found_spot = False

        for idx, market in enumerate(spot_universe, 1):
            market_name = market.get("name", "UNKNOWN")
            token_pair = market.get("tokens", [])
            sz_decimals = market.get("szDecimals", "N/A")

            # Resolve token names
            if len(token_pair) == 2:
                base_idx, quote_idx = token_pair
                base_name = tokens[base_idx].get("name", "?") if base_idx < len(tokens) else "?"
                quote_name = tokens[quote_idx].get("name", "?") if quote_idx < len(tokens) else "?"
                token_info = f"{base_name}/{quote_name} (indices: {base_idx}, {quote_idx})"
            else:
                token_info = f"Invalid token pair: {token_pair}"

            logger.info(
                f"    {idx:3d}. {market_name:20s} {token_info:30s} sz_decimals: {sz_decimals}"
            )

            # Check for ETH (including UETH which is the wrapped ETH on testnet)
            if len(token_pair) == 2:
                base_idx = token_pair[0]
                if base_idx < len(tokens):
                    base_token = tokens[base_idx].get("name", "").upper()
                    if base_token in ("ETH", "UETH"):
                        eth_found_spot = True
                        logger.info(f"         ✓ ETH FOUND on spot market: {market_name}")
                        logger.info(f"         Token: {base_token}")
                        logger.info(f"         Full metadata: {market}")

        if not eth_found_spot:
            logger.warning("  ⚠ ETH NOT FOUND on spot markets")

    except Exception as e:
        logger.error(f"✗ Failed to fetch spot metadata: {e}", exc_info=True)
        return 1

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Perpetual markets loaded: {len(perp_universe)}")
    logger.info(f"Spot markets loaded: {len(spot_universe)}")
    logger.info(f"ETH on perpetual: {'✓ YES' if eth_found_perp else '✗ NO'}")
    logger.info(f"ETH on spot: {'✓ YES' if eth_found_spot else '✗ NO'}")
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
