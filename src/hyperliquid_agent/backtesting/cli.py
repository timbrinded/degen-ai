"""CLI entry point for regime backtesting."""

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

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


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace

    Raises:
        SystemExit: If arguments are invalid
    """
    parser = argparse.ArgumentParser(
        description="Run regime detection backtest on historical Hyperliquid data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 3-month backtest with default settings
  %(prog)s --start-date 2024-01-01 --end-date 2024-03-31

  # Run 1-year backtest with hourly sampling
  %(prog)s --start-date 2023-01-01 --end-date 2023-12-31 --interval 1h

  # Run backtest for specific assets
  %(prog)s --start-date 2024-01-01 --end-date 2024-03-31 --assets BTC,ETH,SOL

  # Save results to custom directory
  %(prog)s --start-date 2024-01-01 --end-date 2024-03-31 --output ./my_backtest
        """,
    )

    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Backtest start date in ISO 8601 format (e.g., 2024-01-01)",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="Backtest end date in ISO 8601 format (e.g., 2024-03-31)",
    )

    parser.add_argument(
        "--interval",
        type=str,
        default="4h",
        choices=["1h", "4h", "1d"],
        help="Sampling interval for data points (default: 4h)",
    )

    parser.add_argument(
        "--assets",
        type=str,
        default="BTC,ETH",
        help="Comma-separated list of asset symbols (default: BTC,ETH)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="./backtest_results",
        help="Output directory for backtest results (default: ./backtest_results)",
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config.toml",
        help="Path to configuration file (default: config.toml)",
    )

    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> tuple[datetime, datetime, list[str]]:
    """Validate and parse command-line arguments.

    Args:
        args: Parsed arguments namespace

    Returns:
        Tuple of (start_date, end_date, assets)

    Raises:
        ValueError: If arguments are invalid
    """
    # Parse ISO 8601 date strings
    try:
        start_date = datetime.fromisoformat(args.start_date)
    except ValueError as e:
        raise ValueError(
            f"Invalid start-date format: {args.start_date}. "
            f"Expected ISO 8601 format (e.g., 2024-01-01). Error: {e}"
        ) from e

    try:
        end_date = datetime.fromisoformat(args.end_date)
    except ValueError as e:
        raise ValueError(
            f"Invalid end-date format: {args.end_date}. "
            f"Expected ISO 8601 format (e.g., 2024-03-31). Error: {e}"
        ) from e

    # Validate end-date > start-date
    if end_date <= start_date:
        raise ValueError(
            f"End date ({end_date.date()}) must be after start date ({start_date.date()})"
        )

    # Validate dates are not in future
    now = datetime.now()
    if start_date > now:
        raise ValueError(f"Start date ({start_date.date()}) cannot be in the future")

    if end_date > now:
        raise ValueError(f"End date ({end_date.date()}) cannot be in the future")

    # Parse comma-separated asset list
    assets = [asset.strip().upper() for asset in args.assets.split(",")]
    if not assets:
        raise ValueError("At least one asset must be specified")

    # Remove duplicates while preserving order
    seen = set()
    assets = [asset for asset in assets if not (asset in seen or seen.add(asset))]  # type: ignore[func-returns-value]

    return start_date, end_date, assets


async def run_backtest_async(
    config_path: str,
    start_date: datetime,
    end_date: datetime,
    interval: str,
    assets: list[str],
    output_dir: Path,
) -> None:
    """Run backtest asynchronously.

    Args:
        config_path: Path to configuration file
        start_date: Backtest start timestamp
        end_date: Backtest end timestamp
        interval: Sampling interval
        assets: List of asset symbols
        output_dir: Output directory for results

    Raises:
        Exception: If backtest fails
    """
    # Load config
    logger.info(f"Loading configuration from {config_path}")
    cfg = load_config(config_path)

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

    # Create regime detector with default config
    regime_detector_config = RegimeDetectorConfig()
    regime_detector = RegimeDetector(config=regime_detector_config)

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


def main() -> None:
    """Main CLI entry point.

    Parses arguments, validates inputs, orchestrates backtest execution,
    and handles errors.

    Raises:
        SystemExit: On error or completion
    """
    # Parse arguments
    try:
        args = parse_arguments()
    except SystemExit:
        raise

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Validate arguments
    try:
        start_date, end_date, assets = validate_arguments(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Convert output path
    output_dir = Path(args.output)

    # Display configuration
    print("\n" + "=" * 80)
    print("REGIME BACKTEST CONFIGURATION")
    print("=" * 80)
    print(f"Start Date: {start_date.date()}")
    print(f"End Date: {end_date.date()}")
    print(f"Interval: {args.interval}")
    print(f"Assets: {', '.join(assets)}")
    print(f"Output Directory: {output_dir.absolute()}")
    print(f"Config File: {args.config}")
    print("=" * 80 + "\n")

    # Run backtest
    try:
        asyncio.run(
            run_backtest_async(
                config_path=args.config,
                start_date=start_date,
                end_date=end_date,
                interval=args.interval,
                assets=assets,
                output_dir=output_dir,
            )
        )
    except KeyboardInterrupt:
        print("\n\nBacktest interrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n\nBacktest failed: {e}", file=sys.stderr)
        logger.error("Backtest failed", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
