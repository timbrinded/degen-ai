"""CLI commands for regime backtesting."""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path

import typer

from hyperliquid_agent.backtesting.historical_data import HistoricalDataManager
from hyperliquid_agent.backtesting.reports import ReportGenerator
from hyperliquid_agent.backtesting.runner import BacktestRunner
from hyperliquid_agent.backtesting.signal_reconstructor import SignalReconstructor
from hyperliquid_agent.config import load_config
from hyperliquid_agent.governance.regime import RegimeDetector, RegimeDetectorConfig
from hyperliquid_agent.signals.cache import SQLiteCacheLayer
from hyperliquid_agent.signals.hyperliquid_provider import HyperliquidProvider
from hyperliquid_agent.signals.processor import ComputedSignalProcessor

logger = logging.getLogger(__name__)


def validate_date_range(start_date: datetime, end_date: datetime) -> None:
    """Validate date range for backtesting.

    Args:
        start_date: Backtest start timestamp
        end_date: Backtest end timestamp

    Raises:
        typer.BadParameter: If date range is invalid
    """
    # Validate end-date > start-date
    if end_date <= start_date:
        raise typer.BadParameter(
            f"End date ({end_date.date()}) must be after start date ({start_date.date()})"
        )

    # Validate dates are not in future
    now = datetime.now()
    if start_date > now:
        raise typer.BadParameter(f"Start date ({start_date.date()}) cannot be in the future")

    if end_date > now:
        raise typer.BadParameter(f"End date ({end_date.date()}) cannot be in the future")


async def _run_backtest_async(
    cfg,
    start_date: datetime,
    end_date: datetime,
    interval: str,
    assets: list[str],
    output_dir: Path,
) -> None:
    """Run backtest asynchronously.

    Args:
        cfg: Loaded configuration object
        start_date: Backtest start timestamp
        end_date: Backtest end timestamp
        interval: Sampling interval
        assets: List of asset symbols
        output_dir: Path for results

    Raises:
        Exception: If backtest fails
    """

    # Initialize components
    logger.info("Initializing components...")

    # Create cache layer
    cache_db_path = cfg.signals.db_path if cfg.signals else "state/signal_cache.db"
    cache = SQLiteCacheLayer(db_path=cache_db_path)

    # Create Hyperliquid Info API client
    from hyperliquid.info import Info

    info = Info(base_url=cfg.hyperliquid.base_url, skip_ws=True)

    # Create Hyperliquid provider
    hyperliquid_provider = HyperliquidProvider(
        info=info,
        cache=cache,
    )

    # Create historical data manager
    historical_data_manager = HistoricalDataManager(
        hyperliquid_provider=hyperliquid_provider,
        cache=cache,
    )

    # Create computed signal processor
    computed_processor = ComputedSignalProcessor(cache=cache)

    # Create signal reconstructor
    signal_reconstructor = SignalReconstructor(
        processor=computed_processor,
    )

    # Validate governance config exists
    if cfg.governance is None:
        logger.error("Error: [governance] section missing in config file")
        raise ValueError("Governance configuration is required for backtesting")

    # Type narrowing: assign to local variable after None check
    governance = cfg.governance

    # Create regime detector with config from TOML file
    regime_detector_config = RegimeDetectorConfig(
        confirmation_cycles_required=governance.regime_detector.get(
            "confirmation_cycles_required", 3
        ),
        hysteresis_enter_threshold=governance.regime_detector.get(
            "hysteresis_enter_threshold", 0.7
        ),
        hysteresis_exit_threshold=governance.regime_detector.get("hysteresis_exit_threshold", 0.4),
        event_lock_window_hours_before=governance.regime_detector.get(
            "event_lock_window_hours_before", 2
        ),
        event_lock_window_hours_after=governance.regime_detector.get(
            "event_lock_window_hours_after", 1
        ),
        llm_provider=governance.regime_detector.get("llm_provider"),
        llm_model=governance.regime_detector.get("llm_model"),
        llm_temperature=governance.regime_detector.get("llm_temperature"),
    )
    regime_detector = RegimeDetector(
        config=regime_detector_config,
        llm_config=cfg.llm,
    )

    # Create backtest runner
    backtest_runner = BacktestRunner(
        historical_data_manager=historical_data_manager,
        signal_reconstructor=signal_reconstructor,
        regime_detector=regime_detector,
    )

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir.absolute()}")

    # Execute backtest
    logger.info("Starting backtest execution...")
    start_time = time.time()

    try:
        summary = await backtest_runner.run_backtest(
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            assets=assets,
        )
    except Exception as e:
        logger.error(f"Backtest execution failed: {e}", exc_info=True)
        raise

    execution_time = time.time() - start_time

    # Generate reports
    logger.info("Generating reports...")
    report_generator = ReportGenerator()

    try:
        # Generate summary report
        report_generator.generate_summary_report(
            summary=summary,
            output_dir=output_dir,
        )

        # Generate CSV export
        csv_path = output_dir / "results.csv"
        report_generator.generate_csv_export(
            summary=summary,
            output_path=csv_path,
        )

        # Generate visualization
        viz_path = output_dir / "timeline.png"
        report_generator.generate_visualization(
            summary=summary,
            output_path=viz_path,
        )

    except Exception as e:
        logger.error(f"Report generation failed: {e}", exc_info=True)
        raise

    # Display summary statistics to console
    print("\n" + "=" * 80)
    print("BACKTEST COMPLETE")
    print("=" * 80)
    print(f"\nExecution Time: {execution_time:.1f} seconds")
    print("\nResults:")
    print(f"  Total Points: {summary.total_points}")
    print(f"  Collected Points: {len(summary.results)}")
    print(f"  Skipped Points: {summary.skipped_points}")
    skip_percentage = (
        (summary.skipped_points / summary.total_points * 100) if summary.total_points > 0 else 0
    )
    print(f"  Skip Rate: {skip_percentage:.1f}%")

    # Display regime distribution
    if summary.results:
        from collections import Counter

        regime_counts = Counter(r.regime for r in summary.results)
        total = len(summary.results)
        print("\nRegime Distribution:")
        for regime, count in sorted(regime_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total * 100) if total > 0 else 0
            print(f"  {regime:20s}: {percentage:6.2f}%")

    # Display output file paths
    print("\nGenerated Reports:")
    print(f"  Summary: {output_dir / 'summary.txt'}")
    print(f"  CSV Data: {output_dir / 'results.csv'}")
    print(f"  Visualization: {output_dir / 'timeline.png'}")
    print("\n" + "=" * 80 + "\n")


def backtest_command(
    start_date: str = typer.Option(
        ...,
        "--start-date",
        help="Backtest start date in ISO 8601 format (e.g., 2024-01-01)",
    ),
    end_date: str = typer.Option(
        ...,
        "--end-date",
        help="Backtest end date in ISO 8601 format (e.g., 2024-03-31)",
    ),
    interval: str = typer.Option(
        "4h",
        "--interval",
        help="Sampling interval for data points (1h, 4h, 1d)",
    ),
    assets: str = typer.Option(
        "BTC,ETH",
        "--assets",
        help="Comma-separated list of asset symbols",
    ),
    output: Path = typer.Option(
        Path("./backtest_results"),
        "--output",
        help="Output directory for backtest results",
    ),
    config: Path = typer.Option(
        Path("config.toml"),
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    clear_cache: bool = typer.Option(
        False,
        "--clear-cache",
        help="Clear cached historical data before running backtest",
    ),
) -> None:
    """Run regime detection backtest on historical Hyperliquid data.

    Examples:

      # Run 3-month backtest with default settings
      degen backtest --start-date 2024-01-01 --end-date 2024-03-31

      # Run 1-year backtest with hourly sampling
      degen backtest --start-date 2023-01-01 --end-date 2023-12-31 --interval 1h

      # Run backtest for specific assets
      degen backtest --start-date 2024-01-01 --end-date 2024-03-31 --assets BTC,ETH,SOL

      # Clear cache before running (useful if data seems stale or corrupt)
      degen backtest --start-date 2024-06-01 --end-date 2024-07-01 --clear-cache
    """
    # Load config first to get log level
    cfg = load_config(config)

    # Clear cache if requested
    if clear_cache:
        cache_db_path = cfg.signals.db_path if cfg.signals else "state/signal_cache.db"
        cache_path = Path(cache_db_path)
        if cache_path.exists():
            cache_path.unlink()
            print(f"✓ Cache cleared: {cache_path}")
        else:
            print(f"ℹ No cache found at: {cache_path}")

    # Setup logging with level from config
    log_level = getattr(logging, cfg.agent.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info(f"Logging configured at level: {cfg.agent.log_level}")
    logger.info(f"Configuration loaded from {config}")

    # Parse and validate dates
    try:
        start_dt = datetime.fromisoformat(start_date)
    except ValueError as e:
        raise typer.BadParameter(
            f"Invalid start-date format: {start_date}. "
            f"Expected ISO 8601 format (e.g., 2024-01-01). Error: {e}"
        ) from e

    try:
        end_dt = datetime.fromisoformat(end_date)
    except ValueError as e:
        raise typer.BadParameter(
            f"Invalid end-date format: {end_date}. "
            f"Expected ISO 8601 format (e.g., 2024-03-31). Error: {e}"
        ) from e

    validate_date_range(start_dt, end_dt)

    # Validate interval
    if interval not in ["1h", "4h", "1d"]:
        raise typer.BadParameter(f"Invalid interval: {interval}. Must be one of: 1h, 4h, 1d")

    # Parse asset list
    asset_list = [asset.strip().upper() for asset in assets.split(",")]
    if not asset_list:
        raise typer.BadParameter("At least one asset must be specified")

    # Remove duplicates while preserving order
    seen = set()
    asset_list = [a for a in asset_list if not (a in seen or seen.add(a))]  # type: ignore[func-returns-value]

    # Display configuration
    typer.echo("\n" + "=" * 80)
    typer.echo("REGIME BACKTEST CONFIGURATION")
    typer.echo("=" * 80)
    typer.echo(f"Start Date: {start_dt.date()}")
    typer.echo(f"End Date: {end_dt.date()}")
    typer.echo(f"Interval: {interval}")
    typer.echo(f"Assets: {', '.join(asset_list)}")
    typer.echo(f"Output Directory: {output.absolute()}")
    typer.echo(f"Config File: {config}")
    typer.echo("=" * 80 + "\n")

    # Run backtest
    try:
        asyncio.run(
            _run_backtest_async(
                cfg=cfg,
                start_date=start_dt,
                end_date=end_dt,
                interval=interval,
                assets=asset_list,
                output_dir=output,
            )
        )
    except KeyboardInterrupt:
        typer.echo("\n\nBacktest interrupted by user.", err=True)
        raise typer.Exit(code=130) from None
    except Exception as e:
        typer.echo(f"\n\nBacktest failed: {e}", err=True)
        logger.error("Backtest failed", exc_info=True)
        raise typer.Exit(code=1) from e
