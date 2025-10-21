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


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
