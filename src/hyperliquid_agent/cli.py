"""CLI entry point for the Hyperliquid trading agent."""

from pathlib import Path

import typer

app = typer.Typer()


@app.command()
def start(
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

    typer.echo(f"\n{'=' * 60}")
    typer.echo(f"Account Status {'(STALE)' if state.is_stale else ''}")
    typer.echo(f"{'=' * 60}")
    typer.echo(f"Portfolio Value:    ${state.portfolio_value:,.2f}")
    typer.echo(f"Available Balance:  ${state.available_balance:,.2f}")
    typer.echo(f"Number of Positions: {len(state.positions)}")

    if state.positions:
        typer.echo(f"\n{'=' * 60}")
        typer.echo("Positions:")
        typer.echo(f"{'=' * 60}")
        for pos in state.positions:
            pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
            typer.echo(f"\n{pos.coin} ({pos.market_type.upper()})")
            typer.echo(f"  Size:          {pos.size:,.4f}")
            typer.echo(f"  Entry Price:   ${pos.entry_price:,.2f}")
            typer.echo(f"  Current Price: ${pos.current_price:,.2f}")
            typer.echo(f"  Unrealized PnL: {pnl_sign}${pos.unrealized_pnl:,.2f}")

    typer.echo(f"\n{'=' * 60}\n")


@app.command()
def test_executor(
    config: Path = typer.Option(
        "config.toml",
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    coin: str = typer.Option("BTC", "--coin", help="Coin to test with"),
    action_type: str = typer.Option("buy", "--action", help="Action type: buy, sell, hold, close"),
    market_type: str = typer.Option("perp", "--market", help="Market type: spot or perp"),
    size: float = typer.Option(0.001, "--size", help="Order size"),
    price: float | None = typer.Option(None, "--price", help="Limit price (None for market)"),
) -> None:
    """Test the trade executor with a single action on testnet."""
    from hyperliquid_agent.config import load_config
    from hyperliquid_agent.decision import TradeAction
    from hyperliquid_agent.executor import TradeExecutor

    cfg = load_config(str(config))
    executor = TradeExecutor(cfg.hyperliquid)

    # Create test action
    action = TradeAction(
        action_type=action_type,  # type: ignore
        coin=coin,
        market_type=market_type,  # type: ignore
        size=size,
        price=price,
        reasoning="CLI test execution",
    )

    typer.echo(f"\n{'=' * 60}")
    typer.echo("Testing Trade Executor")
    typer.echo(f"{'=' * 60}")
    typer.echo(f"Action:  {action.action_type.upper()}")
    typer.echo(f"Coin:    {action.coin}")
    typer.echo(f"Market:  {action.market_type.upper()}")
    typer.echo(f"Size:    {action.size}")
    typer.echo(f"Price:   {'MARKET' if action.price is None else f'${action.price:,.2f}'}")
    typer.echo(f"{'=' * 60}\n")

    # Confirm before executing
    if not typer.confirm("Execute this test order?"):
        typer.echo("Test cancelled.")
        return

    typer.echo("\nExecuting order...")
    result = executor.execute_action(action)

    typer.echo(f"\n{'=' * 60}")
    typer.echo("Execution Result")
    typer.echo(f"{'=' * 60}")
    typer.echo(f"Success:  {result.success}")
    if result.order_id:
        typer.echo(f"Order ID: {result.order_id}")
    if result.error:
        typer.echo(f"Error:    {result.error}")
    typer.echo(f"{'=' * 60}\n")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
