"""LLM-based regime classification logic."""

import logging
from datetime import datetime

from hyperliquid_agent.governance.regime import RegimeClassification, RegimeSignals
from hyperliquid_agent.llm_client import LLMClient


def classify_regime_with_llm(
    signals: RegimeSignals,
    llm_client: LLMClient,
    logger: logging.Logger,
) -> RegimeClassification:
    """Classify market regime using LLM analysis.

    This replaces the boolean logic with LLM-based pattern recognition that:
    1. Uses multi-timeframe returns as PRIMARY signals
    2. Considers technical indicators as CONFIRMING signals
    3. Differentiates trending-bull from trending-bear
    4. Handles ambiguous scenarios naturally

    Args:
        signals: Market signals including price context
        llm_client: Centralized LLM client
        logger: Logger instance

    Returns:
        RegimeClassification with regime, confidence, and reasoning
    """
    # Build prompt with all signals
    prompt = _build_regime_classification_prompt(signals)

    try:
        # Query LLM using centralized client
        response = llm_client.query(prompt)

        # Parse JSON response
        classification_data = llm_client.parse_json_response(response)

        # Validate classification data
        _validate_classification_data(classification_data)

        # Create classification object
        classification = RegimeClassification(
            regime=classification_data["regime"],
            confidence=classification_data["confidence"],
            reasoning=classification_data.get("reasoning", "No reasoning provided"),
            timestamp=datetime.now(),
            signals=signals,
        )

        logger.info(
            f"LLM regime classification: {classification.regime} "
            f"(confidence: {classification.confidence:.2f})",
            extra={
                "governance_event": "llm_regime_classified",
                "regime": classification.regime,
                "confidence": classification.confidence,
                "reasoning": classification.reasoning[:100],  # Truncate for logging
            },
        )

        return classification

    except Exception as e:
        logger.error(f"LLM regime classification failed: {e}", exc_info=True)

        # Fallback to simple heuristic
        return _fallback_classification(signals, logger)


def _build_regime_classification_prompt(signals: RegimeSignals) -> str:
    """Build prompt for LLM regime classification.

    Args:
        signals: Market signals including price context

    Returns:
        Formatted prompt string
    """
    pc = signals.price_context

    return f"""Analyze the following crypto market data and classify the market regime.

PRICE PERFORMANCE (PRIMARY SIGNALS):
- Current Price: ${pc.current_price:.2f}
- 1-day return: {pc.return_1d:+.2f}%
- 7-day return: {pc.return_7d:+.2f}%
- 30-day return: {pc.return_30d:+.2f}%
- 90-day return: {pc.return_90d:+.2f}%

PRICE vs MOVING AVERAGES:
- Distance from 20-day SMA: {pc.sma20_distance:+.2f}%
- Distance from 50-day SMA: {pc.sma50_distance:+.2f}%

MARKET STRUCTURE:
- Making higher highs: {"Yes" if pc.higher_highs else "No"}
- Making higher lows: {"Yes" if pc.higher_lows else "No"}

TECHNICAL INDICATORS (CONFIRMING SIGNALS):
- ADX (trend strength): {signals.adx:.1f}
- 24h Realized Volatility: {signals.realized_vol_24h:.1%}
- Average Funding Rate: {signals.avg_funding_rate:.4f}
- Bid-Ask Spread: {signals.bid_ask_spread_bps:.1f} bps

Classify the regime as ONE of:
- "trending-bull": Sustained upward price movement with positive returns
- "trending-bear": Sustained downward price movement with negative returns
- "range-bound": Sideways price action with small cumulative moves
- "carry-friendly": Positive funding + low volatility (profitable to hold longs)
- "unknown": Unclear or transitional market state

CLASSIFICATION GUIDELINES:
1. Returns are the PRIMARY signal - use them first
   - Sustained positive returns (>10% over 30d or >5% over 7d) + higher highs = trending-bull
   - Sustained negative returns (<-10% over 30d or <-5% over 7d) + lower lows = trending-bear
   - Small moves (<5% over 30d) with tight range = range-bound

2. Technical indicators are CONFIRMING signals, not primary
   - High ADX + high vol confirms a trend but doesn't define it
   - Low ADX + low vol confirms range-bound
   - Don't require extreme values (ADX 80%, vol 80%) to detect trends

3. Direction matters
   - Differentiate bull trends from bear trends explicitly
   - "trending" alone is deprecated - always specify direction

4. Funding + volatility define carry regime
   - Positive funding (>0.01%) + low vol (<40%) = carry-friendly
   - This can coexist with a bull trend

5. Use "unknown" sparingly
   - Only for truly ambiguous transitions
   - Most markets fit one of the four main regimes

Respond in JSON format:
{{
  "regime": "trending-bull|trending-bear|range-bound|carry-friendly|unknown",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation focusing on key factors (1-2 sentences)"
}}

Consider the FULL context - don't focus on just one indicator."""


def _validate_classification_data(data: dict) -> None:
    """Validate parsed classification data from LLM response.

    Args:
        data: Parsed JSON data from LLM

    Raises:
        ValueError: If data is invalid
    """
    # Validate required fields
    if "regime" not in data or "confidence" not in data:
        raise ValueError("LLM response missing required fields: regime, confidence")

    # Validate regime value
    valid_regimes = [
        "trending-bull",
        "trending-bear",
        "range-bound",
        "carry-friendly",
        "unknown",
    ]
    if data["regime"] not in valid_regimes:
        raise ValueError(f"Invalid regime value: {data['regime']}")

    # Validate confidence is between 0 and 1
    confidence = float(data["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"Confidence must be between 0 and 1, got {confidence}")


def _fallback_classification(
    signals: RegimeSignals,
    logger: logging.Logger,
) -> RegimeClassification:
    """Fallback to simple heuristic if LLM fails.

    Uses basic rules based on returns as primary signal.

    Args:
        signals: Market signals
        logger: Logger instance

    Returns:
        RegimeClassification with best-guess regime
    """
    pc = signals.price_context

    logger.warning("Using fallback classification due to LLM failure")

    # Simple rules based on returns
    if pc.return_30d > 10 and pc.higher_highs:
        regime = "trending-bull"
        confidence = 0.6
        reasoning = "Fallback: 30d returns >10% with higher highs"
    elif pc.return_30d < -10:
        regime = "trending-bear"
        confidence = 0.6
        reasoning = "Fallback: 30d returns <-10%"
    elif abs(pc.return_30d) < 5 and signals.realized_vol_24h < 0.3:
        regime = "range-bound"
        confidence = 0.6
        reasoning = "Fallback: Small 30d moves with low volatility"
    elif signals.avg_funding_rate > 0.01 and signals.realized_vol_24h < 0.4:
        regime = "carry-friendly"
        confidence = 0.5
        reasoning = "Fallback: Positive funding with moderate vol"
    else:
        regime = "unknown"
        confidence = 0.4
        reasoning = "Fallback: Ambiguous market state"

    return RegimeClassification(
        regime=regime,
        confidence=confidence,
        reasoning=reasoning,
        timestamp=datetime.now(),
        signals=signals,
    )
