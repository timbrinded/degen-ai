"""Enhanced position monitoring with time-scale signals for governance."""

from typing import Literal

from hyperliquid_agent.monitor import PositionMonitor
from hyperliquid_agent.signals import (
    EnhancedAccountState,
    FastSignalCollector,
    MediumSignalCollector,
    SlowSignalCollector,
)


class EnhancedPositionMonitor(PositionMonitor):
    """Enhanced position monitor that collects time-scale-appropriate signals.

    Extends the base PositionMonitor to collect additional market signals
    organized by decision time-scale (fast/medium/slow loops).
    """

    def __init__(self, *args, **kwargs):
        """Initialize enhanced monitor with signal collectors."""
        super().__init__(*args, **kwargs)
        self.fast_collector = FastSignalCollector(self.info)
        self.medium_collector = MediumSignalCollector(self.info)
        self.slow_collector = SlowSignalCollector(self.info)

    def get_current_state_with_signals(
        self, loop_type: Literal["fast", "medium", "slow"]
    ) -> EnhancedAccountState:
        """Get account state with appropriate signals for loop type.

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
            timestamp=base_state.timestamp,
            is_stale=base_state.is_stale,
        )

        # Collect signals based on loop type
        if loop_type in ["fast", "medium", "slow"]:
            enhanced.fast_signals = self.fast_collector.collect(base_state)

        if loop_type in ["medium", "slow"]:
            enhanced.medium_signals = self.medium_collector.collect(base_state)

        if loop_type == "slow":
            enhanced.slow_signals = self.slow_collector.collect(base_state)

        return enhanced
