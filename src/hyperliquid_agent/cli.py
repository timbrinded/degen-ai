"""CLI entry point for the Hyperliquid trading agent."""

from pathlib import Path

import typer
from hyperliquid.info import Info

from hyperliquid_agent.backtesting.cli import backtest_command
from hyperliquid_agent.identity_registry import AssetIdentityRegistry, default_assets_config_path

app = typer.Typer()

# Register backtest command
app.command(name="backtest")(backtest_command)


def _create_governed_agent(config_path: str):
    """Helper to create a GovernedTradingAgent instance from config.

    Args:
        config_path: Path to configuration file

    Returns:
        Tuple of (Config, GovernedTradingAgent)

    Raises:
        typer.Exit: If governance config is missing
    """
    from hyperliquid_agent.config import load_config
    from hyperliquid_agent.governance.governor import GovernorConfig
    from hyperliquid_agent.governance.regime import RegimeDetectorConfig
    from hyperliquid_agent.governance.tripwire import TripwireConfig
    from hyperliquid_agent.governed_agent import GovernedAgentConfig, GovernedTradingAgent

    cfg = load_config(config_path)

    if cfg.governance is None:
        typer.echo("Error: [governance] section missing in config file", err=True)
        raise typer.Exit(code=1)

    # Type narrowing: assign to local variable after None check
    governance = cfg.governance

    # Convert config dicts to proper types
    governor_config = GovernorConfig(
        minimum_advantage_over_cost_bps=governance.governor.get(
            "minimum_advantage_over_cost_bps", 50.0
        ),
        cooldown_after_change_minutes=governance.governor.get("cooldown_after_change_minutes", 60),
        partial_rotation_pct_per_cycle=governance.governor.get(
            "partial_rotation_pct_per_cycle", 25.0
        ),
        state_persistence_path=governance.governor.get(
            "state_persistence_path", "state/governor.json"
        ),
    )

    regime_config = RegimeDetectorConfig(
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

    tripwire_config = TripwireConfig(
        min_margin_ratio=governance.tripwire.get("min_margin_ratio", 0.15),
        liquidation_proximity_threshold=governance.tripwire.get(
            "liquidation_proximity_threshold", 0.25
        ),
        daily_loss_limit_pct=governance.tripwire.get("daily_loss_limit_pct", 5.0),
        max_data_staleness_seconds=governance.tripwire.get("max_data_staleness_seconds", 300),
        max_api_failure_count=governance.tripwire.get("max_api_failure_count", 3),
    )

    gov_config = GovernedAgentConfig(
        governor=governor_config,
        regime_detector=regime_config,
        tripwire=tripwire_config,
        fast_loop_interval_seconds=governance.fast_loop_interval_seconds,
        medium_loop_interval_minutes=governance.medium_loop_interval_minutes,
        slow_loop_interval_hours=governance.slow_loop_interval_hours,
    )

    agent = GovernedTradingAgent(cfg, gov_config)
    return cfg, agent


@app.command()
def start(
    config: Path = typer.Option(
        "config.toml",
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    governed: bool = typer.Option(
        False,
        "--governed",
        "-g",
        help="Run in governed mode with multi-timescale decision-making",
    ),
    async_mode: bool = typer.Option(
        True,
        "--async/--sync",
        help="Use async concurrent loop execution (default: async)",
    ),
) -> None:
    """Start the Hyperliquid trading agent."""
    import asyncio

    from hyperliquid_agent.config import load_config

    if governed:
        cfg, agent = _create_governed_agent(str(config))

        typer.echo("Starting agent in GOVERNED mode...")
        if cfg.governance:
            typer.echo(
                f"  Fast loop: every {cfg.governance.fast_loop_interval_seconds}s | "
                f"Medium loop: every {cfg.governance.medium_loop_interval_minutes}m | "
                f"Slow loop: every {cfg.governance.slow_loop_interval_hours}h"
            )

        if async_mode:
            typer.echo("  Execution mode: ASYNC (concurrent loops)")
            asyncio.run(agent.run_async())
        else:
            typer.echo("  Execution mode: SYNC (sequential loops)")
            agent.run()
    else:
        from hyperliquid_agent.agent import TradingAgent
        from hyperliquid_agent.config import load_config

        cfg = load_config(str(config))
        typer.echo("Starting agent in STANDARD mode...")
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
    from hyperliquid_agent.price_service import AssetPriceService

    cfg = load_config(str(config))
    assets_config = default_assets_config_path()
    info = Info(cfg.hyperliquid.base_url, skip_ws=True)
    identity_registry = AssetIdentityRegistry(assets_config, info)
    identity_registry.load()
    price_service = AssetPriceService(info, identity_registry)
    monitor = PositionMonitor(
        cfg.hyperliquid,
        identity_registry=identity_registry,
        price_service=price_service,
    )

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
def gov_plan(
    config: Path = typer.Option(
        "config.toml",
        "--config",
        "-c",
        help="Path to configuration file",
    ),
) -> None:
    """Show active governance plan status."""
    _, agent = _create_governed_agent(str(config))

    # Get plan status
    status = agent.get_active_plan_status()

    typer.echo(f"\n{'=' * 70}")
    typer.echo("ACTIVE PLAN STATUS")
    typer.echo(f"{'=' * 70}")

    if not status["has_active_plan"]:
        typer.echo(f"\n{status['message']}")
        typer.echo(f"\n{'=' * 70}\n")
        return

    typer.echo(f"\nPlan ID:          {status['plan_id']}")
    typer.echo(f"Strategy:         {status['strategy_name']} (v{status['strategy_version']})")
    typer.echo(f"Status:           {status['status'].upper()}")
    typer.echo(f"Objective:        {status['objective']}")
    typer.echo(f"Time Horizon:     {status['time_horizon']}")
    typer.echo(f"Target Duration:  {status['target_holding_period_hours']}h")

    typer.echo(f"\n{'-' * 70}")
    typer.echo("TIMING")
    typer.echo(f"{'-' * 70}")
    typer.echo(f"Created:          {status['created_at']}")
    typer.echo(f"Activated:        {status['activated_at']}")
    typer.echo(
        f"Dwell Time:       {status['dwell_elapsed_minutes']:.1f} / {status['minimum_dwell_minutes']} min"
    )
    typer.echo(f"Cooldown:         {status['cooldown_elapsed_minutes']:.1f} min")
    typer.echo(f"Can Review:       {'✓ YES' if status['can_review'] else '✗ NO'}")
    typer.echo(f"Review Reason:    {status['review_reason']}")

    if status["rebalance_progress_pct"] > 0:
        typer.echo(f"Rebalance:        {status['rebalance_progress_pct']:.1f}% complete")

    typer.echo(f"\n{'-' * 70}")
    typer.echo("TARGET ALLOCATIONS")
    typer.echo(f"{'-' * 70}")
    for alloc in status["target_allocations"]:
        typer.echo(
            f"  {alloc['coin']:8s} {alloc['target_pct']:6.2f}% ({alloc['market_type']}, {alloc['leverage']}x)"
        )

    typer.echo(f"\n{'-' * 70}")
    typer.echo("RISK BUDGET")
    typer.echo(f"{'-' * 70}")
    typer.echo(f"Max Leverage:     {status['risk_budget']['max_leverage']}x")
    typer.echo(f"Max Adverse Exc:  {status['risk_budget']['max_adverse_excursion_pct']}%")
    typer.echo(f"Max Drawdown:     {status['risk_budget']['plan_max_drawdown_pct']}%")

    typer.echo(f"\n{'-' * 70}")
    typer.echo("REGIME COMPATIBILITY")
    typer.echo(f"{'-' * 70}")
    typer.echo(f"Compatible:       {', '.join(status['compatible_regimes'])}")
    typer.echo(f"Avoid:            {', '.join(status['avoid_regimes'])}")

    typer.echo(f"\n{'=' * 70}\n")


@app.command()
def gov_regime(
    config: Path = typer.Option(
        "config.toml",
        "--config",
        "-c",
        help="Path to configuration file",
    ),
) -> None:
    """Show current regime classification status."""
    _, agent = _create_governed_agent(str(config))

    # Get regime status
    status = agent.get_regime_status()

    typer.echo(f"\n{'=' * 70}")
    typer.echo("REGIME CLASSIFICATION STATUS")
    typer.echo(f"{'=' * 70}")

    typer.echo(f"\nCurrent Regime:   {status['current_regime'].upper()}")
    typer.echo(f"History Length:   {status['history_length']} classifications")

    if status["in_event_lock"]:
        typer.echo("\n⚠️  EVENT LOCK ACTIVE")
        typer.echo(f"    {status['event_lock_reason']}")

    typer.echo(f"\n{'-' * 70}")
    typer.echo("CONFIGURATION")
    typer.echo(f"{'-' * 70}")
    typer.echo(f"Confirmation Cycles:  {status['confirmation_cycles_required']}")
    typer.echo(f"Enter Threshold:      {status['hysteresis_enter_threshold']:.2f}")
    typer.echo(f"Exit Threshold:       {status['hysteresis_exit_threshold']:.2f}")

    if status["recent_classifications"]:
        typer.echo(f"\n{'-' * 70}")
        typer.echo("RECENT CLASSIFICATIONS")
        typer.echo(f"{'-' * 70}")
        for classification in status["recent_classifications"]:
            typer.echo(
                f"  {classification['timestamp'][:19]} | "
                f"{classification['regime']:15s} | "
                f"confidence: {classification['confidence']:.2f}"
            )

    typer.echo(f"\n{'=' * 70}\n")


@app.command()
def gov_tripwire(
    config: Path = typer.Option(
        "config.toml",
        "--config",
        "-c",
        help="Path to configuration file",
    ),
) -> None:
    """Show tripwire status and active alerts."""
    _, agent = _create_governed_agent(str(config))

    # Get tripwire status
    status = agent.get_tripwire_status()

    typer.echo(f"\n{'=' * 70}")
    typer.echo("TRIPWIRE STATUS")
    typer.echo(f"{'=' * 70}")

    typer.echo(f"\nActive Tripwires: {status['active_tripwires']}")

    if status["active_tripwires"] > 0:
        typer.echo("\n⚠️  ALERTS ACTIVE")
        typer.echo(f"\n{'-' * 70}")
        typer.echo("TRIGGERED EVENTS")
        typer.echo(f"{'-' * 70}")
        for event in status["events"]:
            severity_icon = "🔴" if event["severity"] == "critical" else "🟡"
            typer.echo(f"\n{severity_icon} {event['severity'].upper()} - {event['category']}")
            typer.echo(f"   Trigger: {event['trigger']}")
            typer.echo(f"   Action:  {event['action']}")
            typer.echo(f"   Time:    {event['timestamp'][:19]}")
            if event["details"]:
                typer.echo(f"   Details: {event['details']}")
    else:
        typer.echo("\n✓ All systems nominal - no tripwires active")

    typer.echo(f"\n{'-' * 70}")
    typer.echo("CURRENT STATE")
    typer.echo(f"{'-' * 70}")
    typer.echo(f"Portfolio Value:  ${status['current_state']['portfolio_value']:,.2f}")
    typer.echo(f"Daily Loss:       {status['current_state']['daily_loss_pct']:.2f}%")
    typer.echo(f"API Failures:     {status['current_state']['api_failure_count']}")

    typer.echo(f"\n{'-' * 70}")
    typer.echo("CONFIGURATION")
    typer.echo(f"{'-' * 70}")
    typer.echo(f"Min Margin Ratio:         {status['config']['min_margin_ratio']:.2f}")
    typer.echo(
        f"Liquidation Threshold:    {status['config']['liquidation_proximity_threshold']:.2f}"
    )
    typer.echo(f"Daily Loss Limit:         {status['config']['daily_loss_limit_pct']:.1f}%")
    typer.echo(f"Max Data Staleness:       {status['config']['max_data_staleness_seconds']}s")
    typer.echo(f"Max API Failures:         {status['config']['max_api_failure_count']}")

    typer.echo(f"\n{'=' * 70}\n")


@app.command()
def gov_metrics(
    config: Path = typer.Option(
        "config.toml",
        "--config",
        "-c",
        help="Path to configuration file",
    ),
) -> None:
    """Show plan performance metrics."""
    _, agent = _create_governed_agent(str(config))

    # Get performance metrics
    metrics = agent.get_plan_performance_metrics()

    typer.echo(f"\n{'=' * 70}")
    typer.echo("PLAN PERFORMANCE METRICS")
    typer.echo(f"{'=' * 70}")

    if not metrics["has_active_metrics"]:
        typer.echo(f"\n{metrics['message']}")
        typer.echo(f"Completed Plans: {metrics['completed_plans_count']}")
        typer.echo(f"\n{'=' * 70}\n")
        return

    typer.echo(f"\nPlan ID:          {metrics['plan_id']}")
    typer.echo(f"Start Time:       {metrics['start_time']}")
    typer.echo(f"Duration:         {metrics['duration_hours']:.2f} hours")

    typer.echo(f"\n{'-' * 70}")
    typer.echo("PERFORMANCE")
    typer.echo(f"{'-' * 70}")
    pnl_sign = "+" if metrics["total_pnl"] >= 0 else ""
    typer.echo(f"Total PnL:        {pnl_sign}${metrics['total_pnl']:,.2f}")
    typer.echo(f"Risk Taken:       {metrics['total_risk_taken']:.2f}")
    typer.echo(f"PnL per Risk:     {metrics['pnl_per_unit_risk']:.4f}")

    typer.echo(f"\n{'-' * 70}")
    typer.echo("EXECUTION QUALITY")
    typer.echo(f"{'-' * 70}")
    typer.echo(f"Total Trades:     {metrics['total_trades']}")
    typer.echo(f"Winning Trades:   {metrics['winning_trades']}")
    typer.echo(f"Hit Rate:         {metrics['hit_rate']:.1%}")
    typer.echo(f"Avg Slippage:     {metrics['avg_slippage_bps']:.2f} bps")

    typer.echo(f"\n{'-' * 70}")
    typer.echo("PLAN ADHERENCE")
    typer.echo(f"{'-' * 70}")
    typer.echo(f"Avg Drift:        {metrics['avg_drift_from_targets_pct']:.2f}%")
    typer.echo(f"Rebalances:       {metrics['rebalance_count']}")

    typer.echo(f"\n{'-' * 70}")
    typer.echo("TRACKING")
    typer.echo(f"{'-' * 70}")
    typer.echo(f"Completed Plans:  {metrics['completed_plans_count']}")
    typer.echo(f"Shadow Portfolios: {metrics['shadow_portfolios_count']}")

    typer.echo(f"\n{'=' * 70}\n")


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
    import asyncio

    from hyperliquid.info import Info

    from hyperliquid_agent.config import load_config
    from hyperliquid_agent.decision import TradeAction
    from hyperliquid_agent.executor import TradeExecutor
    from hyperliquid_agent.market_registry import MarketRegistry

    cfg = load_config(str(config))

    # Initialize and hydrate market registry
    info = Info(cfg.hyperliquid.base_url, skip_ws=True)
    registry = MarketRegistry(info)
    asyncio.run(registry.hydrate())

    executor = TradeExecutor(cfg.hyperliquid, registry, risk_config=cfg.risk)

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


@app.command("assets-validate")
def assets_validate(
    base_url: str = typer.Option("https://api.hyperliquid.xyz", help="Hyperliquid API base URL"),
    config_path: Path = typer.Option(
        default_assets_config_path(),
        exists=True,
        resolve_path=True,
        help="Path to asset identity config JSON",
    ),
):
    """Validate asset identity configuration against exchange metadata."""

    info = Info(str(base_url), skip_ws=True)
    registry = AssetIdentityRegistry(config_path, info)
    registry.load()

    identities = list(registry.identities())

    typer.echo("Loaded identities:")
    for identity in identities:
        typer.echo(
            f"  - {identity.canonical_symbol}: wallet={identity.wallet_symbol}"
            f" perp={identity.perp_symbol or 'N/A'}"
            f" spot_aliases={list(identity.spot_aliases)}"
        )

    # Gather exchange metadata sets
    perp_universe = {
        asset.get("name", "").upper()
        for asset in info.meta().get("universe", [])
        if asset.get("name")
    }

    spot_tokens = info.spot_meta().get("tokens", [])
    spot_canonical = set()
    for token in spot_tokens:
        name = token.get("name", "").upper()
        if not name:
            continue
        if name.startswith("U") and len(name) > 1:
            spot_canonical.add(name[1:])
        spot_canonical.add(name)

    identity_set = {identity.canonical_symbol for identity in identities}

    missing_perp = sorted(perp_universe - identity_set)
    missing_spot = sorted({s for s in spot_canonical if not registry.resolve(s)})

    if missing_perp:
        typer.echo("\nPerp markets missing from config:")
        for symbol in missing_perp:
            typer.echo(f"  - {symbol}")
    else:
        typer.echo("\nAll perp markets present in config.")

    if missing_spot:
        typer.echo("\nSpot markets missing from config:")
        for symbol in missing_spot:
            typer.echo(f"  - {symbol}")
    else:
        typer.echo("\nAll spot markets present in config.")

    # Validate each identity resolves to spot/perp descriptors when expected
    typer.echo("\nDescriptor validation:")
    for identity in identities:
        spot_descriptor = registry.get_spot_market(identity)
        perp_descriptor = registry.get_perp_market(identity)

        if identity.spot_aliases or identity.wallet_symbol:
            status = "OK" if spot_descriptor else "MISSING"
            typer.echo(f"  - {identity.canonical_symbol} spot descriptor: {status}")
        if identity.perp_symbol:
            status = "OK" if perp_descriptor else "MISSING"
            typer.echo(f"  - {identity.canonical_symbol} perp descriptor: {status}")

    typer.echo("\nValidation complete.")
