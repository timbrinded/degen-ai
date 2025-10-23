"""Signal service bridging synchronous governance with async signal collection."""

import asyncio
import logging
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from hyperliquid_agent.monitor import AccountState
from hyperliquid_agent.signals.models import (
    FastLoopSignals,
    MediumLoopSignals,
    SlowLoopSignals,
)

logger = logging.getLogger(__name__)


@dataclass
class SignalRequest:
    """Request for signal collection."""

    signal_type: Literal["fast", "medium", "slow"]
    account_state: AccountState
    timestamp: datetime


@dataclass
class SignalResponse:
    """Response from signal collection."""

    signal_type: Literal["fast", "medium", "slow"]
    signals: FastLoopSignals | MediumLoopSignals | SlowLoopSignals
    timestamp: datetime
    error: str | None = None


class SignalService:
    """Bridge between synchronous governance and async signal collection.

    Runs async event loop in background thread, communicates via thread-safe queues.
    """

    def __init__(self, config: dict | None = None):
        """Initialize signal service.

        Args:
            config: Signal configuration dictionary
        """
        self.config = config or {}
        self.request_queue: queue.Queue = queue.Queue()
        self.response_queue: queue.Queue = queue.Queue()
        self.background_thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.shutdown_event = threading.Event()

    def start(self):
        """Start background thread with async event loop."""
        if self.background_thread and self.background_thread.is_alive():
            logger.warning("Signal service already started")
            return

        self.shutdown_event.clear()
        self.background_thread = threading.Thread(
            target=self._run_async_loop, daemon=True, name="SignalCollectionThread"
        )
        self.background_thread.start()
        logger.info("Signal service started")

    def stop(self):
        """Gracefully stop background thread."""
        if not self.background_thread or not self.background_thread.is_alive():
            logger.warning("Signal service not running")
            return

        logger.info("Stopping signal service...")
        self.shutdown_event.set()

        if self.background_thread:
            self.background_thread.join(timeout=5.0)

            if self.background_thread.is_alive():
                logger.warning("Signal service thread did not stop gracefully")
            else:
                logger.info("Signal service stopped")

    def _run_async_loop(self):
        """Run async event loop in background thread."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._process_requests())
        except Exception as e:
            logger.error(f"Error in signal service event loop: {e}")
        finally:
            self.loop.close()
            logger.info("Signal service event loop closed")

    async def _process_requests(self):
        """Process signal collection requests from queue."""
        # Import here to avoid circular dependencies
        from hyperliquid_agent.signals.orchestrator import SignalOrchestrator

        orchestrator = SignalOrchestrator(self.config)

        while not self.shutdown_event.is_set():
            try:
                # Non-blocking queue check with timeout
                try:
                    request = self.request_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # Process request asynchronously
                try:
                    response = await orchestrator.collect_signals(request)
                    self.response_queue.put(response)
                except Exception as e:
                    logger.error(f"Error processing signal request: {e}")
                    # Put error response in queue
                    error_response = SignalResponse(
                        signal_type=request.signal_type,
                        signals=self._get_fallback_signals(request.signal_type),
                        timestamp=datetime.now(),
                        error=str(e),
                    )
                    self.response_queue.put(error_response)

            except Exception as e:
                logger.error(f"Unexpected error in request processing loop: {e}")
                await asyncio.sleep(0.1)

    def collect_signals_sync(
        self,
        signal_type: Literal["fast", "medium", "slow"],
        account_state: AccountState,
        timeout_seconds: float = 30.0,
    ) -> FastLoopSignals | MediumLoopSignals | SlowLoopSignals:
        """Synchronous interface for governance system to request signals.

        This is called from the main governance thread.

        Args:
            signal_type: Type of signals to collect
            account_state: Current account state
            timeout_seconds: Timeout for signal collection

        Returns:
            Collected signals (type depends on signal_type)
        """
        if not self.background_thread or not self.background_thread.is_alive():
            logger.warning("Signal service not running, returning fallback signals")
            return self._get_fallback_signals(signal_type)

        request = SignalRequest(
            signal_type=signal_type, account_state=account_state, timestamp=datetime.now()
        )

        # Put request in queue
        self.request_queue.put(request)

        # Wait for response with timeout
        try:
            response = self.response_queue.get(timeout=timeout_seconds)

            if response.error:
                logger.warning(f"Signal collection error: {response.error}")

            return response.signals

        except queue.Empty:
            logger.error(f"Signal collection timeout after {timeout_seconds}s")
            return self._get_fallback_signals(signal_type)

    def _get_fallback_signals(
        self, signal_type: Literal["fast", "medium", "slow"]
    ) -> FastLoopSignals | MediumLoopSignals | SlowLoopSignals:
        """Get fallback signals when collection fails.

        Args:
            signal_type: Type of signals to return

        Returns:
            Default/fallback signals
        """
        if signal_type == "fast":
            return FastLoopSignals(
                spreads={},
                slippage_estimates={},
                short_term_volatility=0.0,
                micro_pnl=0.0,
                partial_fill_rates={},
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
