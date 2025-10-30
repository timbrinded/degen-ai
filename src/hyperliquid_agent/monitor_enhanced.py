"""Enhanced position monitoring with time-scale signals for governance."""

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

    def get_current_state_with_signals(
        self, loop_type: Literal["fast", "medium", "slow"], timeout_seconds: float = 30.0
    ) -> EnhancedAccountState:
        """Get account state with appropriate signals for loop type.

        Uses SignalService to collect signals asynchronously in background thread,
        with timeout handling and fallback to cached signals on failure.

        Args:
            loop_type: Type of loop requesting state ("fast", "medium", or "slow")
            timeout_seconds: Timeout for signal collection (default: 30.0)

        Returns:
            EnhancedAccountState with signals appropriate for the loop type
        """
        # Get base account state
        base_state = self.get_current_state()

        # Create enhanced state
        enhanced = EnhancedAccountState(
            portfolio_value=base_state.portfolio_value,
            available_balance=base_state.available_balance,
            positions=base_state.positions,
            spot_balances=base_state.spot_balances,
            timestamp=base_state.timestamp,
            is_stale=base_state.is_stale,
        )

        # Collect signals based on loop type using SignalService
        # SignalService handles timeout, fallback to cached signals, and error handling
        try:
            if loop_type in ["fast", "medium", "slow"]:
                from hyperliquid_agent.signals.models import FastLoopSignals

                signals = self.signal_service.collect_signals_sync(
                    signal_type="fast",
                    account_state=base_state,
                    timeout_seconds=timeout_seconds,
                )
                # Type narrowing: we know this is FastLoopSignals because signal_type="fast"
                assert isinstance(signals, FastLoopSignals)
                enhanced.fast_signals = signals

            if loop_type in ["medium", "slow"]:
                from hyperliquid_agent.signals.models import MediumLoopSignals

                signals = self.signal_service.collect_signals_sync(
                    signal_type="medium",
                    account_state=base_state,
                    timeout_seconds=timeout_seconds,
                )
                # Type narrowing: we know this is MediumLoopSignals because signal_type="medium"
                assert isinstance(signals, MediumLoopSignals)
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
