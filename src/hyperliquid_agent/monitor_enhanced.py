"""Enhanced position monitoring with time-scale signals for governance."""

import asyncio
from pathlib import Path
from typing import Literal

from hyperliquid_agent.monitor import PositionMonitor
from hyperliquid_agent.signals import (
    EnhancedAccountState,
    FastSignalCollector,
    MediumSignalCollector,
    SlowSignalCollector,
)
from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.hyperliquid_provider import HyperliquidProvider
from hyperliquid_agent.signals.processor import ComputedSignalProcessor


class EnhancedPositionMonitor(PositionMonitor):
    """Enhanced position monitor that collects time-scale-appropriate signals.

    Extends the base PositionMonitor to collect additional market signals
    organized by decision time-scale (fast/medium/slow loops).
    """

    def __init__(self, *args, **kwargs):
        """Initialize enhanced monitor with signal collectors."""
        super().__init__(*args, **kwargs)

        # Initialize cache and providers
        cache = SQLiteCacheLayer(Path("state/signal_cache.db"))
        hl_provider = HyperliquidProvider(self.info, cache)
        computed_processor = ComputedSignalProcessor(cache)

        # Initialize collectors with async providers
        self.fast_collector = FastSignalCollector(self.info, hl_provider, computed_processor)
        self.medium_collector = MediumSignalCollector(self.info, hl_provider, computed_processor)
        self.slow_collector = SlowSignalCollector(self.info)

    def get_current_state_with_signals(
        self, loop_type: Literal["fast", "medium", "slow"]
    ) -> EnhancedAccountState:
        """Get account state with appropriate signals for loop type (sync wrapper).

        Args:
            loop_type: Type of loop requesting state ("fast", "medium", or "slow")

        Returns:
            EnhancedAccountState with signals appropriate for the loop type
        """
        return asyncio.run(self.get_current_state_with_signals_async(loop_type))

    async def get_current_state_with_signals_async(
        self, loop_type: Literal["fast", "medium", "slow"]
    ) -> EnhancedAccountState:
        """Get account state with appropriate signals for loop type (async).

        Args:
            loop_type: Type of loop requesting state ("fast", "medium", or "slow")

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

        # Collect signals based on loop type
        if loop_type in ["fast", "medium", "slow"]:
            enhanced.fast_signals = await self.fast_collector.collect(base_state)

        if loop_type in ["medium", "slow"]:
            enhanced.medium_signals = await self.medium_collector.collect(base_state)

        if loop_type == "slow":
            enhanced.slow_signals = self.slow_collector.collect(base_state)

        return enhanced
