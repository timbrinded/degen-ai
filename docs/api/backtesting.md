# Backtesting Modules

Backtesting modules provide historical simulation framework for validating strategies and regime detection.

## BacktestRunner

Orchestrates backtest execution across a specified time period.

**Module:** `hyperliquid_agent.backtesting.runner`

### Constructor

```python
def __init__(
    self,
    historical_data_manager: HistoricalDataManager,
    signal_reconstructor: SignalReconstructor,
    regime_detector: RegimeDetector
) -> None
```

Initialize backtest runner with required components.

**Parameters:**

- `historical_data_manager` (HistoricalDataManager): Manager for fetching historical data
- `signal_reconstructor` (SignalReconstructor): Reconstructor for building RegimeSignals
- `regime_detector` (RegimeDetector): Detector for classifying regimes

**Example:**

```python
from hyperliquid_agent.backtesting.runner import BacktestRunner
from hyperliquid_agent.backtesting.historical_data import HistoricalDataManager
from hyperliquid_agent.backtesting.signal_reconstructor import SignalReconstructor
from hyperliquid_agent.governance.regime import RegimeDetector

# Initialize components
data_manager = HistoricalDataManager(hl_provider, cache)
signal_reconstructor = SignalReconstructor(data_manager)
regime_detector = RegimeDetector(config, llm_config)

# Create runner
runner = BacktestRunner(
    data_manager,
    signal_reconstructor,
    regime_detector
)
```

### Methods

#### run_backtest

```python
async def run_backtest(
    self,
    start_date: datetime,
    end_date: datetime,
    interval: str,
    assets: list[str]
) -> BacktestSummary
```

Execute backtest over date range.

**Parameters:**

- `start_date` (datetime): Backtest start timestamp
- `end_date` (datetime): Backtest end timestamp
- `interval` (str): Sampling interval ("1h", "4h", "1d")
- `assets` (list[str]): List of asset symbols to track

**Returns:**

- `BacktestSummary`: Complete backtest results and metadata

**Raises:**

- `ValueError`: If date range is invalid

**Example:**

```python
from datetime import datetime

start = datetime(2024, 1, 1)
end = datetime(2024, 3, 31)

summary = await runner.run_backtest(
    start_date=start,
    end_date=end,
    interval="1h",
    assets=["BTC", "ETH"]
)

print(f"Total points: {summary.total_points}")
print(f"Collected: {len(summary.results)}")
print(f"Skipped: {summary.skipped_points}")
```

### Constants

- `MIN_CONFIDENCE_THRESHOLD` (float): Minimum confidence for including data points (0.3)
- `MAX_SKIP_PERCENTAGE` (float): Warning threshold for skipped points (20.0%)
- `HYPERLIQUID_CANDLE_LIMIT` (int): API candle limit (5000)
- `REQUIRED_LOOKBACK_PERIODS` (int): Lookback periods for indicators (50)

## HistoricalDataManager

Manages historical data fetching and caching for backtesting.

**Module:** `hyperliquid_agent.backtesting.historical_data`

### Constructor

```python
def __init__(
    self,
    hyperliquid_provider: HyperliquidProvider,
    cache: SQLiteCacheLayer
) -> None
```

Initialize historical data manager.

**Parameters:**

- `hyperliquid_provider` (HyperliquidProvider): Provider for Hyperliquid API access
- `cache` (SQLiteCacheLayer): SQLite cache layer for data persistence

**Example:**

```python
from hyperliquid_agent.backtesting.historical_data import HistoricalDataManager
from hyperliquid_agent.signals.hyperliquid_provider import HyperliquidProvider
from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid.info import Info

info = Info(skip_ws=True)
cache = SQLiteCacheLayer("state/signal_cache.db")
hl_provider = HyperliquidProvider(info, cache)

data_manager = HistoricalDataManager(hl_provider, cache)
```

### Methods

#### fetch_candles_range

```python
async def fetch_candles_range(
    self,
    coin: str,
    interval: str,
    start_time: datetime,
    end_time: datetime
) -> list[Candle]
```

Fetch OHLCV candles for date range with pagination support.

**Parameters:**

- `coin` (str): Trading pair symbol (e.g., "BTC", "ETH")
- `interval` (str): Candle interval (e.g., "1h", "4h", "1d")
- `start_time` (datetime): Start timestamp for data range
- `end_time` (datetime): End timestamp for data range

**Returns:**

- `list[Candle]`: List of Candle objects sorted by timestamp

**Raises:**

- `Exception`: If fetch fails after all retries

**Example:**

```python
from datetime import datetime

candles = await data_manager.fetch_candles_range(
    coin="BTC",
    interval="1h",
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 1, 31)
)

print(f"Fetched {len(candles)} candles")
for candle in candles[:5]:
    print(f"{candle.timestamp}: O={candle.open} H={candle.high} L={candle.low} C={candle.close}")
```

#### fetch_funding_rates_range

```python
async def fetch_funding_rates_range(
    self,
    coin: str,
    start_time: datetime,
    end_time: datetime
) -> list[FundingRate]
```

Fetch funding rate history for date range.

**Parameters:**

- `coin` (str): Trading pair symbol (e.g., "BTC", "ETH")
- `start_time` (datetime): Start timestamp for data range
- `end_time` (datetime): End timestamp for data range

**Returns:**

- `list[FundingRate]`: List of FundingRate objects sorted by timestamp

**Raises:**

- `Exception`: If fetch fails after all retries

**Example:**

```python
funding_rates = await data_manager.fetch_funding_rates_range(
    coin="BTC",
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 1, 31)
)

print(f"Fetched {len(funding_rates)} funding rates")
for rate in funding_rates[:5]:
    print(f"{rate.timestamp}: {rate.rate:.6f}")
```

#### fetch_order_book_snapshot

```python
async def fetch_order_book_snapshot(
    self,
    coin: str,
    timestamp: datetime
) -> OrderBookData | None
```

Fetch order book snapshot closest to timestamp.

**Parameters:**

- `coin` (str): Trading pair symbol (e.g., "BTC", "ETH")
- `timestamp` (datetime): Target timestamp for snapshot

**Returns:**

- `OrderBookData | None`: Order book data or None if not available

**Raises:**

- `Exception`: If fetch fails after all retries

### Constants

- `CACHE_TTL_HISTORICAL` (int): Cache TTL for historical data (7 days)
- `MAX_CANDLES_PER_CHUNK` (int): Maximum candles per API call (1000)
- `MAX_RETRIES` (int): Maximum retry attempts (5)
- `BACKOFF_BASE` (float): Exponential backoff base (2.0)

## ReportGenerator

Generates backtest analysis reports and visualizations.

**Module:** `hyperliquid_agent.backtesting.reports`

### Methods

#### generate_summary_report

```python
def generate_summary_report(
    self,
    summary: BacktestSummary,
    output_dir: Path
) -> None
```

Generate text summary report with regime distribution and transitions.

**Parameters:**

- `summary` (BacktestSummary): Backtest results
- `output_dir` (Path): Directory to save the report

**Raises:**

- `IOError`: If unable to write report file

**Example:**

```python
from hyperliquid_agent.backtesting.reports import ReportGenerator
from pathlib import Path

generator = ReportGenerator()
generator.generate_summary_report(
    summary=backtest_summary,
    output_dir=Path("backtest_results")
)
```

#### generate_csv_export

```python
def generate_csv_export(
    self,
    summary: BacktestSummary,
    output_path: Path
) -> None
```

Export detailed CSV with all data points.

**Parameters:**

- `summary` (BacktestSummary): Backtest results
- `output_path` (Path): Path to save the CSV file

**Raises:**

- `IOError`: If unable to write CSV file

**Example:**

```python
generator.generate_csv_export(
    summary=backtest_summary,
    output_path=Path("backtest_results/results.csv")
)
```

#### generate_visualization

```python
def generate_visualization(
    self,
    summary: BacktestSummary,
    output_path: Path
) -> None
```

Generate time-series plot of regime classifications.

**Parameters:**

- `summary` (BacktestSummary): Backtest results
- `output_path` (Path): Path to save the visualization

**Raises:**

- `IOError`: If unable to write visualization file

**Example:**

```python
generator.generate_visualization(
    summary=backtest_summary,
    output_path=Path("backtest_results/timeline.png")
)
```

### Constants

- `REGIME_COLORS` (dict): Color scheme for regime visualization
- `LOW_CONFIDENCE_THRESHOLD` (float): Low confidence threshold for flagging (0.5)

## Data Models

### BacktestSummary

Complete backtest results and metadata.

**Fields:**

- `results` (list[BacktestResult]): List of all backtest results
- `start_time` (datetime): Backtest start timestamp
- `end_time` (datetime): Backtest end timestamp
- `interval` (str): Sampling interval
- `assets` (list[str]): List of tracked assets
- `total_points` (int): Total timestamps in range
- `skipped_points` (int): Number of skipped timestamps

### BacktestResult

Single backtest data point.

**Fields:**

- `timestamp` (datetime): Data point timestamp
- `regime` (str): Classified regime
- `confidence` (float): Classification confidence (0.0 to 1.0)
- `signals` (RegimeSignals): Reconstructed signals

### Candle

OHLCV candle data.

**Fields:**

- `timestamp` (datetime): Candle timestamp
- `open` (float): Opening price
- `high` (float): Highest price
- `low` (float): Lowest price
- `close` (float): Closing price
- `volume` (float): Trading volume

### FundingRate

Funding rate data point.

**Fields:**

- `timestamp` (datetime): Funding rate timestamp
- `rate` (float): Funding rate value

## Usage Example

Complete backtesting workflow:

```python
import asyncio
from datetime import datetime
from pathlib import Path
from hyperliquid_agent.backtesting.runner import BacktestRunner
from hyperliquid_agent.backtesting.historical_data import HistoricalDataManager
from hyperliquid_agent.backtesting.signal_reconstructor import SignalReconstructor
from hyperliquid_agent.backtesting.reports import ReportGenerator
from hyperliquid_agent.governance.regime import RegimeDetector, RegimeDetectorConfig
from hyperliquid_agent.signals.hyperliquid_provider import HyperliquidProvider
from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid.info import Info

async def run_backtest():
    # Initialize components
    info = Info(skip_ws=True)
    cache = SQLiteCacheLayer("state/signal_cache.db")
    hl_provider = HyperliquidProvider(info, cache)
    
    data_manager = HistoricalDataManager(hl_provider, cache)
    signal_reconstructor = SignalReconstructor(data_manager)
    
    regime_config = RegimeDetectorConfig()
    regime_detector = RegimeDetector(regime_config, llm_config)
    
    # Create runner
    runner = BacktestRunner(
        data_manager,
        signal_reconstructor,
        regime_detector
    )
    
    # Run backtest
    summary = await runner.run_backtest(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 3, 31),
        interval="1h",
        assets=["BTC", "ETH"]
    )
    
    # Generate reports
    output_dir = Path("backtest_results")
    generator = ReportGenerator()
    
    generator.generate_summary_report(summary, output_dir)
    generator.generate_csv_export(summary, output_dir / "results.csv")
    generator.generate_visualization(summary, output_dir / "timeline.png")
    
    print(f"Backtest complete: {len(summary.results)} data points")
    print(f"Results saved to {output_dir}")

# Run the backtest
asyncio.run(run_backtest())
```

## See Also

- [Core Modules](/api/core) - Main agent and execution
- [Governance Modules](/api/governance) - Regime detection
- [Backtesting Guide](/guide/backtesting) - Detailed backtesting tutorial
- [Configuration](/guide/configuration) - Backtesting configuration
