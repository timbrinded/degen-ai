"""Report generation for backtest analysis and visualization."""

import logging
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from hyperliquid_agent.backtesting.models import BacktestSummary

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates backtest analysis reports and visualizations.

    Produces summary statistics, CSV exports, and time-series visualizations
    from backtest results to enable validation and analysis of regime detection.
    """

    # Color scheme for regime visualization
    REGIME_COLORS = {
        "trending": "green",
        "range-bound": "blue",
        "carry-friendly": "yellow",
        "event-risk": "red",
        "unknown": "gray",
    }

    # Low confidence threshold for flagging
    LOW_CONFIDENCE_THRESHOLD = 0.5

    def generate_summary_report(
        self,
        summary: BacktestSummary,
        output_dir: Path,
    ) -> None:
        """Generate text summary report.

        Creates a comprehensive text report including regime distribution,
        transitions, confidence metrics, and data quality statistics.

        Args:
            summary: BacktestSummary with all results
            output_dir: Directory to save the report

        Raises:
            IOError: If unable to write report file
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "summary.txt"

        logger.info(f"Generating summary report: {output_path}")

        # Calculate statistics
        regime_distribution = self._calculate_regime_distribution(summary)
        transitions = self._identify_regime_transitions(summary)
        avg_confidence_per_regime = self._calculate_avg_confidence_per_regime(summary)
        overall_avg_confidence = self._calculate_overall_avg_confidence(summary)

        # Build report content
        lines = []
        lines.append("=" * 80)
        lines.append("BACKTEST SUMMARY REPORT")
        lines.append("=" * 80)
        lines.append("")

        # Configuration
        lines.append("Configuration:")
        lines.append(f"  Start Date: {summary.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  End Date: {summary.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  Interval: {summary.interval}")
        lines.append(f"  Assets: {', '.join(summary.assets)}")
        lines.append("")

        # Data Quality Metrics
        lines.append("Data Quality:")
        lines.append(f"  Total Points: {summary.total_points}")
        lines.append(f"  Collected Points: {len(summary.results)}")
        lines.append(f"  Skipped Points: {summary.skipped_points}")
        skip_percentage = (
            (summary.skipped_points / summary.total_points * 100) if summary.total_points > 0 else 0
        )
        lines.append(f"  Skip Rate: {skip_percentage:.1f}%")
        lines.append(f"  Overall Avg Confidence: {overall_avg_confidence:.3f}")
        lines.append("")

        # Regime Distribution
        lines.append("Regime Distribution:")
        for regime, percentage in sorted(
            regime_distribution.items(), key=lambda x: x[1], reverse=True
        ):
            lines.append(f"  {regime:20s}: {percentage:6.2f}%")
        lines.append("")

        # Average Confidence per Regime
        lines.append("Average Confidence per Regime:")
        for regime, confidence in sorted(
            avg_confidence_per_regime.items(), key=lambda x: x[1], reverse=True
        ):
            lines.append(f"  {regime:20s}: {confidence:.3f}")
        lines.append("")

        # Regime Transitions
        lines.append(f"Regime Transitions ({len(transitions)} total):")
        if transitions:
            lines.append("")
            for i, transition in enumerate(transitions[:20], 1):  # Show first 20
                lines.append(
                    f"  {i:3d}. {transition['timestamp'].strftime('%Y-%m-%d %H:%M')} | "
                    f"{transition['from_regime']:15s} -> {transition['to_regime']:15s} "
                    f"(confidence: {transition['confidence']:.3f})"
                )
            if len(transitions) > 20:
                lines.append(f"  ... and {len(transitions) - 20} more transitions")
        else:
            lines.append("  No regime transitions detected")
        lines.append("")

        # Low Confidence Warnings
        low_confidence_count = sum(
            1 for r in summary.results if r.confidence < self.LOW_CONFIDENCE_THRESHOLD
        )
        if low_confidence_count > 0:
            low_confidence_percentage = (
                (low_confidence_count / len(summary.results) * 100) if summary.results else 0
            )
            lines.append("⚠️  Data Quality Warnings:")
            lines.append(
                f"  {low_confidence_count} data points ({low_confidence_percentage:.1f}%) "
                f"have confidence < {self.LOW_CONFIDENCE_THRESHOLD}"
            )
            lines.append("")

        lines.append("=" * 80)

        # Write report
        report_content = "\n".join(lines)
        output_path.write_text(report_content)

        logger.info(f"Summary report saved to {output_path}")

    def generate_csv_export(
        self,
        summary: BacktestSummary,
        output_path: Path,
    ) -> None:
        """Export detailed CSV with all data points.

        Creates a CSV file with timestamp, regime, confidence, and all
        underlying signal values for each backtest data point.

        Args:
            summary: BacktestSummary with all results
            output_path: Path to save the CSV file

        Raises:
            IOError: If unable to write CSV file
        """
        logger.info(f"Generating CSV export: {output_path}")

        # Build DataFrame from results
        data = []
        for result in summary.results:
            row = {
                "timestamp": result.timestamp,
                "regime": result.regime,
                "confidence": result.confidence,
                "adx": result.signals.adx,
                "price_sma_20": result.signals.price_sma_20,
                "price_sma_50": result.signals.price_sma_50,
                "realized_vol_24h": result.signals.realized_vol_24h,
                "avg_funding_rate": result.signals.avg_funding_rate,
                "bid_ask_spread_bps": result.signals.bid_ask_spread_bps,
                "order_book_depth": result.signals.order_book_depth,
            }
            data.append(row)

        df = pd.DataFrame(data)

        # Only format and export if we have data
        if not df.empty:
            # Format timestamp for readability
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            # Export to CSV
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_path, index=False, float_format="%.6f")

            logger.info(f"CSV export saved to {output_path} ({len(df)} rows)")
        else:
            logger.warning("No data to export - skipping CSV generation")

    def generate_visualization(
        self,
        summary: BacktestSummary,
        output_path: Path,
    ) -> None:
        """Generate time-series plot of regime classifications.

        Creates a visualization with color-coded regime bands, confidence
        score overlay, regime transition markers, and low-confidence flags.

        Args:
            summary: BacktestSummary with all results
            output_path: Path to save the PNG file

        Raises:
            IOError: If unable to write PNG file
        """
        logger.info(f"Generating visualization: {output_path}")

        if not summary.results:
            logger.warning("No results to visualize")
            return

        # Extract data for plotting
        timestamps = [r.timestamp for r in summary.results]
        regimes = [r.regime for r in summary.results]
        confidences = [r.confidence for r in summary.results]

        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

        # Plot 1: Regime timeline with color-coded bands
        self._plot_regime_timeline(ax1, timestamps, regimes, confidences)

        # Plot 2: Confidence score overlay
        self._plot_confidence_timeline(ax2, timestamps, confidences)

        # Format x-axis
        fig.autofmt_xdate()

        # Add title and metadata
        fig.suptitle(
            f"Regime Backtest: {summary.start_time.date()} to {summary.end_time.date()}",
            fontsize=16,
            fontweight="bold",
        )

        # Add metadata text
        metadata_text = (
            f"Interval: {summary.interval} | "
            f"Assets: {', '.join(summary.assets)} | "
            f"Points: {len(summary.results)}/{summary.total_points} "
            f"({(len(summary.results) / summary.total_points * 100):.1f}%)"
        )
        fig.text(0.5, 0.02, metadata_text, ha="center", fontsize=10, style="italic")

        # Adjust layout
        plt.tight_layout(rect=(0, 0.03, 1, 0.97))

        # Save figure
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"Visualization saved to {output_path}")

    def _calculate_regime_distribution(self, summary: BacktestSummary) -> dict[str, float]:
        """Calculate percentage of time in each regime.

        Args:
            summary: BacktestSummary with results

        Returns:
            Dictionary mapping regime to percentage
        """
        if not summary.results:
            return {}

        regime_counts = Counter(r.regime for r in summary.results)
        total = len(summary.results)

        return {regime: (count / total * 100) for regime, count in regime_counts.items()}

    def _identify_regime_transitions(self, summary: BacktestSummary) -> list[dict]:
        """Identify and list regime transitions with timestamps.

        Args:
            summary: BacktestSummary with results

        Returns:
            List of transition dictionaries with timestamp, from_regime, to_regime, confidence
        """
        transitions = []

        for i in range(1, len(summary.results)):
            prev_result = summary.results[i - 1]
            curr_result = summary.results[i]

            if prev_result.regime != curr_result.regime:
                transitions.append(
                    {
                        "timestamp": curr_result.timestamp,
                        "from_regime": prev_result.regime,
                        "to_regime": curr_result.regime,
                        "confidence": curr_result.confidence,
                    }
                )

        return transitions

    def _calculate_avg_confidence_per_regime(self, summary: BacktestSummary) -> dict[str, float]:
        """Calculate average confidence score per regime type.

        Args:
            summary: BacktestSummary with results

        Returns:
            Dictionary mapping regime to average confidence
        """
        regime_confidences: dict[str, list[float]] = {}

        for result in summary.results:
            if result.regime not in regime_confidences:
                regime_confidences[result.regime] = []
            regime_confidences[result.regime].append(result.confidence)

        return {
            regime: sum(confidences) / len(confidences)
            for regime, confidences in regime_confidences.items()
        }

    def _calculate_overall_avg_confidence(self, summary: BacktestSummary) -> float:
        """Calculate overall average confidence across all results.

        Args:
            summary: BacktestSummary with results

        Returns:
            Average confidence score
        """
        if not summary.results:
            return 0.0

        return sum(r.confidence for r in summary.results) / len(summary.results)

    def _plot_regime_timeline(
        self,
        ax: plt.Axes,
        timestamps: list,
        regimes: list[str],
        confidences: list[float],
    ) -> None:
        """Plot regime timeline with color-coded bands.

        Args:
            ax: Matplotlib axes to plot on
            timestamps: List of timestamps
            regimes: List of regime classifications
            confidences: List of confidence scores
        """
        # Create regime bands
        current_regime = regimes[0]
        start_idx = 0

        for i in range(1, len(regimes)):
            if regimes[i] != current_regime:
                # Plot band for previous regime
                color = self.REGIME_COLORS.get(current_regime, "gray")
                ax.axvspan(
                    timestamps[start_idx],
                    timestamps[i - 1],
                    alpha=0.3,
                    color=color,
                    label=current_regime
                    if current_regime not in ax.get_legend_handles_labels()[1]
                    else "",
                )

                # Mark transition with vertical line
                ax.axvline(timestamps[i], color="black", linestyle="--", alpha=0.3, linewidth=0.5)

                # Update for next regime
                current_regime = regimes[i]
                start_idx = i

        # Plot final regime band
        color = self.REGIME_COLORS.get(current_regime, "gray")
        ax.axvspan(
            timestamps[start_idx],
            timestamps[-1],
            alpha=0.3,
            color=color,
            label=current_regime if current_regime not in ax.get_legend_handles_labels()[1] else "",
        )

        # Flag low-confidence periods with dashed lines
        for ts, conf in zip(timestamps, confidences, strict=True):
            if conf < self.LOW_CONFIDENCE_THRESHOLD:
                ax.axvline(ts, color="red", linestyle=":", alpha=0.2, linewidth=0.5)

        ax.set_ylabel("Regime", fontsize=12, fontweight="bold")
        ax.set_title("Regime Classification Timeline", fontsize=14, fontweight="bold")
        ax.legend(loc="upper left", fontsize=10)
        ax.grid(True, alpha=0.3)

    def _plot_confidence_timeline(
        self,
        ax: plt.Axes,
        timestamps: list,
        confidences: list[float],
    ) -> None:
        """Plot confidence score timeline.

        Args:
            ax: Matplotlib axes to plot on
            timestamps: List of timestamps
            confidences: List of confidence scores
        """
        # Plot confidence line
        ax.plot(timestamps, confidences, color="blue", linewidth=1.5, label="Confidence")

        # Add low confidence threshold line
        ax.axhline(
            self.LOW_CONFIDENCE_THRESHOLD,
            color="red",
            linestyle="--",
            alpha=0.5,
            linewidth=1,
            label=f"Low Confidence Threshold ({self.LOW_CONFIDENCE_THRESHOLD})",
        )

        ax.set_xlabel("Timestamp", fontsize=12, fontweight="bold")
        ax.set_ylabel("Confidence Score", fontsize=12, fontweight="bold")
        ax.set_title("Confidence Score Timeline", fontsize=14, fontweight="bold")
        ax.set_ylim(0, 1.05)
        ax.legend(loc="upper left", fontsize=10)
        ax.grid(True, alpha=0.3)
