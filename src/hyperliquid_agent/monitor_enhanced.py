"""Enhanced position monitoring with time-scale signals for governance."""

import asyncio
import logging
from typing import Any, Literal

from hyperliquid_agent.monitor import PositionMonitor
from hyperliquid_agent.signals import EnhancedAccountState
from hyperliquid_agent.signals.service import SignalService

logger = logging.getLogger(__name__)


class EnhancedPositionMonitor(PositionMonitor):
    """Enhanced position monitor that collects time-scale-appropriate signals.

    Extends the base PositionMonitor to collect additional market signals
    organized by decision time-scale (fast/medium/slow loops).

    Uses SignalService to bridge synchronous governance with async signal collection
    via a background thread running an async event loop.
    """

    def __init__(self, *args, **kwargs):
        """Initialize enhanced monitor with signal service.

        Starts background signal collection thread for async data fetching.
        """
        super().__init__(*args, **kwargs)

        # Initialize signal service with configuration
        signal_config = {
            "collection_timeout_seconds": 30.0,
            "cache_db_path": "state/signal_cache.db",
            "enable_caching": True,
        }

        self.signal_service = SignalService(config=signal_config)

        # Start background signal collection thread
        self.signal_service.start()

        # Wait for orchestrator to be ready before proceeding
        if not self.signal_service.wait_until_ready(timeout=10.0):
            logger.warning(
                "Signal service orchestrator did not become ready within timeout. "
                "Signal collection may fail until orchestrator initializes."
            )

        logger.info("Enhanced position monitor initialized with signal service")

    def __del__(self):
        """Cleanup signal service on monitor destruction."""
        self.shutdown()

    def shutdown(self):
        """Gracefully shutdown signal service and cleanup resources."""
        if hasattr(self, "signal_service"):
            logger.info("Shutting down signal service")
            self.signal_service.stop()
            logger.info("Signal service shutdown complete")

    def get_cache_metrics(self) -> dict[str, Any]:
        """Get cache performance metrics from orchestrator.

        Returns:
            Dictionary with cache metrics including:
            - status: "success", "orchestrator_not_available", or "error"
            - providers: Dict of provider-specific cache metrics (if successful)
            - error: Error message (if failed)
        """
        if not hasattr(self, "signal_service") or self.signal_service is None:
            return {
                "status": "orchestrator_not_available",
                "error": "Signal service not initialized",
            }

        try:
            # Get orchestrator from signal service
            orchestrator = self.signal_service.orchestrator

            if orchestrator is None:
                return {
                    "status": "orchestrator_not_available",
                    "error": "Orchestrator not available in signal service",
                }

            # Request cache metrics from orchestrator
            cache_stats = orchestrator.get_cache_metrics()

            return {
                "status": "success",
                "cache": cache_stats,
            }

        except Exception as e:
            logger.warning(f"Failed to get cache metrics: {e}")
            return {"status": "error", "error": str(e)}

    def build_watchlist(self, account_state, active_plan=None) -> list[str]:
        """Build watchlist of coins needing price data.

        Combines current positions, plan target allocations, and major coins
        to create a comprehensive watchlist for price fetching.

        Args:
            account_state: Current account state with positions
            active_plan: Optional active governance plan with target allocations

        Returns:
            List of coin symbols to fetch prices for
        """
        watchlist = set()

        # Add current positions
        for position in account_state.positions:
            watchlist.add(position.coin)

        # Add plan target allocations if available
        if active_plan and hasattr(active_plan, "target_allocations"):
            for allocation in active_plan.target_allocations:
                watchlist.add(allocation.coin)

        # Always include majors for regime detection
        watchlist.update(["BTC", "ETH"])

        logger.debug(f"Built watchlist with {len(watchlist)} coins: {sorted(watchlist)}")
        return list(watchlist)

    def fetch_watchlist_prices(self, watchlist: list[str]) -> dict[str, float]:
        """Fetch lightweight prices for watchlist coins synchronously.

        Fetches mid-prices for all coins in the watchlist using the async
        HyperliquidProvider via the signal service's orchestrator.

        Args:
            watchlist: List of coin symbols to fetch prices for

        Returns:
            Dictionary mapping coin symbols to mid-prices
        """
        if not watchlist:
            return {}

        # Access the orchestrator's HyperliquidProvider
        orchestrator = self.signal_service.orchestrator
        if not orchestrator:
            logger.warning("Orchestrator not available for price fetching")
            return {}

        # Run async price fetching in the signal service's event loop
        async def _fetch_all_prices():
            from hyperliquid_agent.signals.providers import ProviderResponse

            # Type narrowing: we've already checked orchestrator is not None above
            assert orchestrator is not None
            tasks = [orchestrator.hl_provider.fetch_mid_price(coin) for coin in watchlist]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            price_map = {}
            for coin, result in zip(watchlist, results, strict=True):
                if isinstance(result, Exception):
                    logger.debug(f"Failed to fetch price for {coin}: {result}")
                elif isinstance(result, ProviderResponse):
                    # Type narrowing: result is ProviderResponse[float] here
                    price_map[coin] = result.data

            return price_map

        # Submit to the background thread's event loop and wait for result
        try:
            price_map = self.signal_service.run_coroutine_sync(_fetch_all_prices())
            logger.debug(f"Fetched {len(price_map)}/{len(watchlist)} prices for watchlist")
            return price_map
        except Exception as e:
            logger.warning(f"Error fetching watchlist prices: {e}")
            return {}

    def get_market_price(self, coin: str) -> float | None:
        """Get current market price for a specific coin.

        Fetches mid-price for a single coin. Primarily used as a fallback
        when the coin isn't in the main price_map.

        Args:
            coin: Coin symbol (e.g., "BTC", "ETH")

        Returns:
            Mid-price as float, or None if fetch fails
        """
        orchestrator = self.signal_service.orchestrator
        if not orchestrator:
            logger.warning("Orchestrator not available for price fetching")
            return None

        async def _fetch_price():
            # Type narrowing: we've already checked orchestrator is not None above
            assert orchestrator is not None
            result = await orchestrator.hl_provider.fetch_mid_price(coin)
            return result.data

        try:
            price = self.signal_service.run_coroutine_sync(_fetch_price())
            logger.debug(f"Fetched market price for {coin}: {price}")
            return price
        except Exception as e:
            logger.debug(f"Failed to fetch market price for {coin}: {e}")
            return None

    def get_current_state_with_signals(
        self,
        loop_type: Literal["fast", "medium", "slow"],
        timeout_seconds: float = 30.0,
        active_plan=None,
    ) -> EnhancedAccountState:
        """Get account state with appropriate signals for loop type.

        Uses SignalService to collect signals asynchronously in background thread,
        with timeout handling and fallback to cached signals on failure.

        Args:
            loop_type: Type of loop requesting state ("fast", "medium", or "slow")
            timeout_seconds: Timeout for signal collection (default: 30.0)
            active_plan: Optional active governance plan for building watchlist

        Returns:
            EnhancedAccountState with signals appropriate for the loop type
        """
        # Get base account state
        base_state = self.get_current_state()

        # Build watchlist and fetch prices for new positions
        watchlist = self.build_watchlist(base_state, active_plan)
        price_map = self.fetch_watchlist_prices(watchlist)

        # Create enhanced state with price_map
        enhanced = EnhancedAccountState(
            portfolio_value=base_state.portfolio_value,
            available_balance=base_state.available_balance,
            positions=base_state.positions,
            spot_balances=base_state.spot_balances,
            timestamp=base_state.timestamp,
            is_stale=base_state.is_stale,
            price_map=price_map,
        )

        # Collect signals based on loop type using SignalService
        # SignalService handles timeout, fallback to cached signals, and error handling
        try:
            if loop_type in ["fast", "medium", "slow"]:
                from hyperliquid_agent.signals.models import FastLoopSignals, SignalQualityMetadata

                signals = self.signal_service.collect_signals_sync(
                    signal_type="fast",
                    account_state=base_state,
                    timeout_seconds=timeout_seconds,
                )
                # Type narrowing: we expect this to be FastLoopSignals
                if not isinstance(signals, FastLoopSignals):
                    logger.error(
                        f"Expected FastLoopSignals but got {type(signals).__name__}, using fallback"
                    )
                    # Use fallback signals instead of potentially incorrect type
                    signals = FastLoopSignals(
                        spreads={},
                        slippage_estimates={},
                        short_term_volatility=0.0,
                        micro_pnl=0.0,
                        partial_fill_rates={},
                        order_book_depth={},
                        api_latency_ms=0.0,
                        metadata=SignalQualityMetadata.create_fallback(),
                    )
                enhanced.fast_signals = signals

            if loop_type in ["medium", "slow"]:
                from hyperliquid_agent.signals.models import (
                    MediumLoopSignals,
                    SignalQualityMetadata,
                )

                signals = self.signal_service.collect_signals_sync(
                    signal_type="medium",
                    account_state=base_state,
                    timeout_seconds=timeout_seconds,
                )
                # Type narrowing: we expect this to be MediumLoopSignals
                if not isinstance(signals, MediumLoopSignals):
                    logger.error(
                        f"Expected MediumLoopSignals but got {type(signals).__name__}, using fallback"
                    )
                    # Use fallback signals instead of potentially incorrect type
                    signals = MediumLoopSignals(
                        realized_vol_1h=0.0,
                        realized_vol_24h=0.0,
                        trend_score=0.0,
                        funding_basis={},
                        perp_spot_basis={},
                        concentration_ratios={},
                        drift_from_targets={},
                        technical_indicators={},
                        open_interest_change_24h={},
                        oi_to_volume_ratio={},
                        funding_rate_trend={},
                        metadata=SignalQualityMetadata.create_fallback(),
                    )
                enhanced.medium_signals = signals

            if loop_type == "slow":
                from hyperliquid_agent.signals.models import SlowLoopSignals

                signals = self.signal_service.collect_signals_sync(
                    signal_type="slow",
                    account_state=base_state,
                    timeout_seconds=timeout_seconds,
                )
                # Type narrowing: we know this is SlowLoopSignals because signal_type="slow"
                assert isinstance(signals, SlowLoopSignals)
                enhanced.slow_signals = signals

        except Exception as e:
            logger.error(f"Error collecting signals for {loop_type} loop: {e}", exc_info=True)
            # SignalService already provides fallback signals, but log the error
            # The enhanced state will have whatever signals were successfully collected

        return enhanced
