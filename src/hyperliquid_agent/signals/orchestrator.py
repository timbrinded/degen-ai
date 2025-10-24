"""Signal orchestrator for coordinating async signal collection."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from hyperliquid.info import Info

from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.collectors import (
    FastSignalCollector,
    MediumSignalCollector,
    SlowSignalCollector,
)
from hyperliquid_agent.signals.hyperliquid_provider import HyperliquidProvider
from hyperliquid_agent.signals.processor import ComputedSignalProcessor
from hyperliquid_agent.signals.service import SignalRequest, SignalResponse

logger = logging.getLogger(__name__)


class SignalOrchestrator:
    """Orchestrates concurrent signal collection from multiple providers.

    This orchestrator coordinates async data collection from multiple providers,
    handles timeouts and cancellation, and aggregates results with error handling.
    It supports concurrent task spawning for parallel data fetching to minimize
    latency while maintaining reliability through partial success handling.

    Attributes:
        config: Signal configuration dictionary
        cache: SQLite cache layer for data persistence
        hl_provider: Hyperliquid data provider
        computed_processor: Computed signal processor
        fast_collector: Fast loop signal collector
        medium_collector: Medium loop signal collector
        slow_collector: Slow loop signal collector
        default_timeout: Default timeout for signal collection in seconds
    """

    # Default timeouts for different signal types (in seconds)
    DEFAULT_TIMEOUT_FAST = 5.0
    DEFAULT_TIMEOUT_MEDIUM = 15.0
    DEFAULT_TIMEOUT_SLOW = 30.0

    def __init__(self, config: dict | None = None):
        """Initialize signal orchestrator with providers and collectors.

        Args:
            config: Signal configuration dictionary with optional keys:
                - collection_timeout_seconds: Global timeout override
                - cache_db_path: Path to SQLite cache database
                - enable_caching: Whether to enable caching (default: True)
        """
        self.config = config or {}

        # Initialize cache layer
        cache_db_path = self.config.get("cache_db_path", "state/signal_cache.db")
        self.cache = SQLiteCacheLayer(Path(cache_db_path))

        # Initialize Hyperliquid Info API client
        info = Info()

        # Initialize async providers
        self.hl_provider = HyperliquidProvider(info, self.cache)
        self.computed_processor = ComputedSignalProcessor(self.cache)

        # Initialize collectors
        self.fast_collector = FastSignalCollector(info, self.hl_provider, self.computed_processor)
        self.medium_collector = MediumSignalCollector(info)
        self.slow_collector = SlowSignalCollector(info)

        # Get default timeout from config
        self.default_timeout = self.config.get("collection_timeout_seconds", 30.0)

        logger.info(
            f"SignalOrchestrator initialized with cache at {cache_db_path}, "
            f"timeout={self.default_timeout}s"
        )

    async def collect_signals(self, request: SignalRequest) -> SignalResponse:
        """Collect signals based on request type with timeout and error handling.

        This method routes the request to the appropriate collector and handles:
        - Timeout enforcement based on signal type
        - Cancellation support for long-running operations
        - Error aggregation and partial success handling
        - Concurrent task spawning for parallel data fetching

        Args:
            request: Signal collection request with signal_type and account_state

        Returns:
            SignalResponse with collected signals and metadata

        Raises:
            asyncio.TimeoutError: If collection exceeds timeout
            ValueError: If signal_type is unknown
        """
        # Determine timeout based on signal type
        if request.signal_type == "fast":
            timeout = self.config.get("fast_timeout_seconds", self.DEFAULT_TIMEOUT_FAST)
        elif request.signal_type == "medium":
            timeout = self.config.get("medium_timeout_seconds", self.DEFAULT_TIMEOUT_MEDIUM)
        elif request.signal_type == "slow":
            timeout = self.config.get("slow_timeout_seconds", self.DEFAULT_TIMEOUT_SLOW)
        else:
            raise ValueError(f"Unknown signal type: {request.signal_type}")

        logger.debug(f"Collecting {request.signal_type} signals with timeout={timeout}s")

        try:
            # Wrap collection in timeout with cancellation support
            signals = await asyncio.wait_for(
                self._collect_signals_internal(request), timeout=timeout
            )

            return SignalResponse(
                signal_type=request.signal_type,
                signals=signals,
                timestamp=datetime.now(),
                error=None,
            )

        except TimeoutError:
            logger.error(
                f"Signal collection timeout after {timeout}s for {request.signal_type} signals"
            )
            # Return fallback signals with error
            return SignalResponse(
                signal_type=request.signal_type,
                signals=self._get_fallback_signals(request.signal_type),
                timestamp=datetime.now(),
                error=f"Collection timeout after {timeout}s",
            )

        except asyncio.CancelledError:
            logger.warning(f"Signal collection cancelled for {request.signal_type} signals")
            raise

        except Exception as e:
            logger.error(f"Error collecting {request.signal_type} signals: {e}", exc_info=True)
            # Return fallback signals with error
            return SignalResponse(
                signal_type=request.signal_type,
                signals=self._get_fallback_signals(request.signal_type),
                timestamp=datetime.now(),
                error=str(e),
            )

    async def _collect_signals_internal(self, request: SignalRequest):
        """Internal signal collection with concurrent task spawning.

        This method handles the actual signal collection logic, spawning
        concurrent tasks where appropriate for parallel data fetching.

        Args:
            request: Signal collection request

        Returns:
            Collected signals (type depends on request.signal_type)
        """
        if request.signal_type == "fast":
            # Fast signals - now async with concurrent order book fetching
            signals = await self.fast_collector.collect(request.account_state)
            return signals

        elif request.signal_type == "medium":
            # Medium signals - currently sync, will be async in task 8
            loop = asyncio.get_event_loop()
            signals = await loop.run_in_executor(
                None, self.medium_collector.collect, request.account_state
            )
            return signals

        elif request.signal_type == "slow":
            # Slow signals - currently sync, will be async in task 12
            loop = asyncio.get_event_loop()
            signals = await loop.run_in_executor(
                None, self.slow_collector.collect, request.account_state
            )
            return signals

        else:
            raise ValueError(f"Unknown signal type: {request.signal_type}")

    async def collect_concurrent(self, requests: list[SignalRequest]) -> list[SignalResponse]:
        """Collect multiple signal types concurrently using asyncio.gather().

        This method demonstrates concurrent task spawning for parallel data fetching
        across multiple signal types. It handles partial success by continuing even
        if some collections fail.

        Args:
            requests: List of signal collection requests

        Returns:
            List of SignalResponse objects (one per request)
        """
        if not requests:
            return []

        logger.info(f"Collecting {len(requests)} signal types concurrently")

        # Spawn concurrent tasks for all requests
        tasks = [self.collect_signals(request) for request in requests]

        # Use gather with return_exceptions=True for partial success handling
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and handle exceptions
        responses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"Failed to collect {requests[i].signal_type} signals: {result}",
                    exc_info=result,
                )
                # Create error response
                responses.append(
                    SignalResponse(
                        signal_type=requests[i].signal_type,
                        signals=self._get_fallback_signals(requests[i].signal_type),
                        timestamp=datetime.now(),
                        error=str(result),
                    )
                )
            else:
                responses.append(result)

        # Log summary
        success_count = sum(1 for r in responses if r.error is None)
        logger.info(f"Concurrent collection complete: {success_count}/{len(requests)} successful")

        return responses

    def _get_fallback_signals(self, signal_type: str):
        """Get fallback signals when collection fails.

        Args:
            signal_type: Type of signals to return

        Returns:
            Default/fallback signals with safe values
        """
        from hyperliquid_agent.signals.models import (
            FastLoopSignals,
            MediumLoopSignals,
            SignalQualityMetadata,
            SlowLoopSignals,
        )

        if signal_type == "fast":
            return FastLoopSignals(
                spreads={},
                slippage_estimates={},
                short_term_volatility=0.0,
                micro_pnl=0.0,
                partial_fill_rates={},
                order_book_depth={},
                api_latency_ms=0.0,
                metadata=SignalQualityMetadata.create_fallback(),
            )
        elif signal_type == "medium":
            return MediumLoopSignals(
                realized_vol_1h=0.0,
                realized_vol_24h=0.0,
                trend_score=0.0,
                funding_basis={},
                perp_spot_basis={},
                concentration_ratios={},
                drift_from_targets={},
            )
        else:  # slow
            return SlowLoopSignals(
                macro_events_upcoming=[],
                cross_asset_risk_on_score=0.0,
                venue_health_score=0.5,
                liquidity_regime="medium",
            )

    async def shutdown(self):
        """Gracefully shutdown orchestrator and cleanup resources.

        This method should be called when the orchestrator is no longer needed
        to ensure proper cleanup of cache connections and other resources.
        """
        logger.info("Shutting down SignalOrchestrator")
        self.cache.close()
        logger.info("SignalOrchestrator shutdown complete")

    def get_health_status(self) -> dict:
        """Get health status of all providers for monitoring.

        Returns:
            Dictionary with health metrics for each provider
        """
        return {
            "orchestrator": "healthy",
            "providers": {
                "hyperliquid": self.hl_provider.get_health_status(),
                # Future: Add other providers as they are implemented
            },
            "cache": {
                "metrics": self.cache.get_metrics(),
            },
        }
