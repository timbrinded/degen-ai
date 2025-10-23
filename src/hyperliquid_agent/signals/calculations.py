"""Pure calculation functions for signal processing."""


def calculate_realized_volatility(candles: list[dict]) -> float:
    """Calculate realized volatility from candle data.

    Args:
        candles: List of candle dictionaries with OHLC data

    Returns:
        Realized volatility as a decimal (e.g., 0.02 = 2%)
    """
    if len(candles) < 2:
        return 0.0

    closes = [float(c["c"]) for c in candles]
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]

    if not returns:
        return 0.0

    # Calculate standard deviation of returns
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    return variance**0.5


def calculate_spread_bps(best_bid: float, best_ask: float) -> float:
    """Calculate bid-ask spread in basis points.

    Args:
        best_bid: Best bid price
        best_ask: Best ask price

    Returns:
        Spread in basis points
    """
    mid_price = (best_bid + best_ask) / 2
    return ((best_ask - best_bid) / mid_price) * 10000


def calculate_sma(prices: list[float], period: int) -> float:
    """Calculate Simple Moving Average.

    Args:
        prices: List of prices
        period: Number of periods for SMA

    Returns:
        SMA value
    """
    if len(prices) < period:
        return 0.0
    return sum(prices[-period:]) / period


def calculate_trend_score(current_price: float, sma_20: float, sma_50: float) -> float:
    """Calculate trend score from price and SMAs.

    Args:
        current_price: Current price
        sma_20: 20-period SMA
        sma_50: 50-period SMA

    Returns:
        Trend score from -1 (strong down) to +1 (strong up)
    """
    if sma_20 > sma_50:
        # Uptrend: measure strength by distance from SMA
        return min(1.0, (current_price - sma_20) / sma_20 * 10)
    # Downtrend
    return max(-1.0, (current_price - sma_20) / sma_20 * 10)
