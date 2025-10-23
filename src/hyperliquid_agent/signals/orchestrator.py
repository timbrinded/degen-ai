"""Signal orchestrator for coordinating async signal collection."""

import logging

from hyperliquid_agent.signals.collectors import (
    FastSignalCollector,
    MediumSignalCollector,
    SlowSignalCollector,
)
from hyperliquid_agent.signals.service import SignalRequest, SignalResponse

logger = logging.getLogger(__name__)


class SignalOrchestrator:
    """Orchestrates concurrent signal collection from multiple providers.

    This is a placeholder implementation that will be enhanced in later tasks
    to support async providers and concurrent collection.
    """

    def __init__(self, config: dict | None = None):
        """Initialize signal orchestrator.

        Args:
            config: Signal configuration dictionary
        """
        self.config = config or {}

        # Import Info here to avoid circular dependencies
        from hyperliquid.info import Info

        info = Info()

        # Initialize collectors with existing sync implementation
        self.fast_collector = FastSignalCollector(info)
        self.medium_collector = MediumSignalCollector(info)
        self.slow_collector = SlowSignalCollector(info)

    async def collect_signals(self, request: SignalRequest) -> SignalResponse:
        """Collect signals based on request type.

        Args:
            request: Signal collection request

        Returns:
            Signal response with collected signals
        """
        from datetime import datetime

        try:
            if request.signal_type == "fast":
                signals = self.fast_collector.collect(request.account_state)
            elif request.signal_type == "medium":
                signals = self.medium_collector.collect(request.account_state)
            elif request.signal_type == "slow":
                signals = self.slow_collector.collect(request.account_state)
            else:
                raise ValueError(f"Unknown signal type: {request.signal_type}")

            return SignalResponse(
                signal_type=request.signal_type, signals=signals, timestamp=datetime.now()
            )

        except Exception as e:
            logger.error(f"Error collecting {request.signal_type} signals: {e}")
            raise
