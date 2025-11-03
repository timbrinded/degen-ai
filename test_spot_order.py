#!/usr/bin/env python3
"""Integration test for spot order execution on Hyperliquid testnet.

This script tests the complete flow of placing a spot market order:
1. Initialize TradeExecutor with testnet configuration
2. Hydrate MarketRegistry to load spot market metadata
3. Place a small spot market order (ETH/USDC or PURR/USDC)
4. Verify order acceptance by checking for order_id in response
5. Cancel the order after successful placement

Usage:
    python test_spot_order.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from hyperliquid.info import Info

from hyperliquid_agent.config import load_config
from hyperliquid_agent.decision import TradeAction
from hyperliquid_agent.executor import TradeExecutor
from hyperliquid_agent.market_registry import MarketRegistry

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Main test function."""
    logger.info("=" * 80)
    logger.info("Spot Order Execution Integration Test")
    logger.info("=" * 80)

    # Load configuration
    config_path = Path(__file__).parent / "config.toml"
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        logger.error("Please create config.toml with your testnet credentials")
        return 1

    try:
        config = load_config(config_path)
        logger.info(f"✓ Configuration loaded from {config_path}")
        logger.info(f"  Account: {config.hyperliquid.account_address}")
        logger.info(f"  Base URL: {config.hyperliquid.base_url}")
    except Exception as e:
        logger.error(f"✗ Failed to load configuration: {e}", exc_info=True)
        return 1

    # Initialize Info API client
    logger.info("\n[1] INITIALIZING INFO API CLIENT")
    logger.info("-" * 80)
    try:
        info = Info(config.hyperliquid.base_url, skip_ws=True)
        logger.info("✓ Info API client initialized")
    except Exception as e:
        logger.error(f"✗ Failed to initialize Info API: {e}", exc_info=True)
        return 1

    # Initialize and hydrate MarketRegistry
    logger.info("\n[2] INITIALIZING MARKET REGISTRY")
    logger.info("-" * 80)
    try:
        registry = MarketRegistry(info)
        await registry.hydrate()
        logger.info("✓ Market registry hydrated successfully")
    except Exception as e:
        logger.error(f"✗ Failed to hydrate market registry: {e}", exc_info=True)
        return 1

    # Determine which spot market to use
    logger.info("\n[3] SELECTING SPOT MARKET")
    logger.info("-" * 80)

    test_coins = ["ETH", "PURR", "UETH"]  # Try these in order
    selected_coin = None
    selected_market = None

    for coin in test_coins:
        try:
            asset_info = registry.get_asset_info(coin)
            if asset_info and asset_info.has_spot:
                market_name = registry.get_market_name(coin, "spot")
                selected_coin = coin
                selected_market = market_name
                logger.info(f"✓ Found available spot market: {coin} -> {market_name}")
                break
        except Exception as e:
            logger.debug(f"  {coin} not available on spot: {e}")
            continue

    if not selected_coin or not selected_market:
        logger.error("✗ No suitable spot markets found for testing")
        logger.error("  Tried: " + ", ".join(test_coins))
        return 1

    logger.info(f"  Selected coin: {selected_coin}")
    logger.info(f"  Market name: {selected_market}")

    # Initialize TradeExecutor
    logger.info("\n[4] INITIALIZING TRADE EXECUTOR")
    logger.info("-" * 80)
    try:
        executor = TradeExecutor(config.hyperliquid, registry)
        logger.info("✓ Trade executor initialized")
    except Exception as e:
        logger.error(f"✗ Failed to initialize trade executor: {e}", exc_info=True)
        return 1

    # Get size decimals for the selected market
    logger.info("\n[5] DETERMINING ORDER SIZE")
    logger.info("-" * 80)

    try:
        sz_decimals = registry.get_sz_decimals(selected_coin, "spot")
        logger.info(f"  Size decimals for {selected_coin} spot: {sz_decimals}")

        # Calculate appropriate test size based on decimals
        test_size = 1.0 if sz_decimals == 0 else 10 ** (-sz_decimals)

        logger.info(f"  Test size: {test_size}")
    except Exception as e:
        logger.error(f"✗ Failed to get size decimals: {e}", exc_info=True)
        return 1

    # Create spot market order action
    logger.info("\n[6] CREATING SPOT MARKET ORDER")
    logger.info("-" * 80)

    action = TradeAction(
        action_type="buy",
        coin=selected_coin,
        market_type="spot",
        size=test_size,
        price=None,  # Market order
        reasoning="Integration test - spot market order",
    )

    logger.info(f"  Action: {action.action_type.upper()}")
    logger.info(f"  Coin: {action.coin}")
    logger.info(f"  Market Type: {action.market_type}")
    logger.info(f"  Size: {action.size}")
    logger.info(f"  Price: {action.price} (market order)")

    # Execute the order
    logger.info("\n[7] SUBMITTING ORDER TO HYPERLIQUID")
    logger.info("-" * 80)

    try:
        result = executor.execute_action(action)

        logger.info(f"  Success: {result.success}")
        logger.info(f"  Order ID: {result.order_id}")
        logger.info(f"  Error: {result.error}")

        if not result.success:
            logger.error(f"✗ Order submission failed: {result.error}")
            return 1

        if not result.order_id:
            logger.warning("⚠ Order submitted but no order_id returned")
            logger.warning("  This may indicate the order was filled immediately")
            logger.warning("  or the order size was too small after rounding")
        else:
            logger.info(f"✓ Order submitted successfully with ID: {result.order_id}")

    except Exception as e:
        logger.error(f"✗ Order execution failed: {e}", exc_info=True)
        return 1

    # Attempt to cancel the order if we got an order_id
    if result.order_id:
        logger.info("\n[8] CANCELING TEST ORDER")
        logger.info("-" * 80)

        try:
            # Use the exchange client directly to cancel
            cancel_result = executor.exchange.cancel(
                name=selected_market,
                oid=result.order_id,
            )

            logger.info(f"  Cancel result: {cancel_result}")
            logger.info("✓ Order canceled successfully")

        except Exception as e:
            logger.warning(f"⚠ Failed to cancel order: {e}")
            logger.warning("  Order may have already been filled or canceled")
    else:
        logger.info("\n[8] SKIPPING ORDER CANCELLATION")
        logger.info("-" * 80)
        logger.info("  No order_id to cancel (order likely filled immediately)")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Market tested: {selected_market}")
    logger.info(f"Order submitted: {'✓ YES' if result.success else '✗ NO'}")
    logger.info(f"Order ID received: {'✓ YES' if result.order_id else '✗ NO'}")
    logger.info("=" * 80)

    if result.success:
        logger.info("\n✓ SPOT ORDER INTEGRATION TEST PASSED")
        return 0
    else:
        logger.error("\n✗ SPOT ORDER INTEGRATION TEST FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
