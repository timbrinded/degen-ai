"""CLI entry point for the Hyperliquid trading agent."""

from pathlib import Path

import typer

app = typer.Typer()


@app.command()
def run(
    config: Path = typer.Option(
        "config.toml",
        "--config",
        "-c",
        help="Path to configuration file",
    ),
) -> None:
    """Start the Hyperliquid trading agent."""
    from hyperliquid_agent.agent import TradingAgent
    from hyperliquid_agent.config import load_config

    cfg = load_config(str(config))
    agent = TradingAgent(cfg)
    agent.run()


@app.command()
def status(
    config: Path = typer.Option(
        "config.toml",
        "--config",
        "-c",
        help="Path to configuration file",
    ),
) -> None:
    """Check current account status and positions."""
    from hyperliquid_agent.config import load_config
    from hyperliquid_agent.monitor import PositionMonitor

    cfg = load_config(str(config))
    monitor = PositionMonitor(cfg.hyperliquid)
    
    typer.echo("Fetching account state...")
    state = monitor.get_current_state()
    
    typer.echo(f"\n{'='*60}")
    typer.echo(f"Account Status {'(STALE)' if state.is_stale else ''}")
    typer.echo(f"{'='*60}")
    typer.echo(f"Portfolio Value:    ${state.portfolio_value:,.2f}")
    typer.echo(f"Available Balance:  ${state.available_balance:,.2f}")
    typer.echo(f"Number of Positions: {len(state.positions)}")
    
    if state.positions:
        typer.echo(f"\n{'='*60}")
        typer.echo("Positions:")
        typer.echo(f"{'='*60}")
        for pos in state.positions:
            pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
            typer.echo(f"\n{pos.coin} ({pos.market_type.upper()})")
            typer.echo(f"  Size:          {pos.size:,.4f}")
            typer.echo(f"  Entry Price:   ${pos.entry_price:,.2f}")
            typer.echo(f"  Current Price: ${pos.current_price:,.2f}")
            typer.echo(f"  Unrealized PnL: {pnl_sign}${pos.unrealized_pnl:,.2f}")
    
    typer.echo(f"\n{'='*60}\n")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
