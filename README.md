# Hyperliquid Trading Agent

Autonomous trading agent for the Hyperliquid platform using LLM-based decision making.

## Overview

This agent runs continuously, monitoring positions, consulting an LLM for trading decisions, and executing trades in both spot and perpetual markets with the goal of maximizing portfolio value.

## Features

- Autonomous 24/7 trading operation
- LLM-powered decision making (OpenAI or Anthropic)
- Support for both spot and perpetual markets
- Configurable prompt templates
- Structured logging with file and console output
- Modular architecture for easy extension

## Project Structure

```
hyperliquid-trading-agent/
├── src/
│   └── hyperliquid_agent/
│       ├── __init__.py
│       ├── cli.py          # CLI entry point
│       ├── agent.py        # Main orchestration loop
│       ├── monitor.py      # Position monitoring
│       ├── decision.py     # LLM decision engine
│       ├── executor.py     # Trade execution
│       └── config.py       # Configuration management
├── prompts/
│   └── default.txt         # Default LLM prompt template
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── logs/                   # Log files directory
├── config.toml.example     # Example configuration
└── pyproject.toml
```

## Installation

1. Clone the repository
2. Install dependencies using uv:

```bash
uv pip install -e .
```

## Configuration

1. Copy the example configuration:

```bash
cp config.toml.example config.toml
```

2. Edit `config.toml` with your credentials:
   - Hyperliquid account address and secret key
   - LLM provider API key (OpenAI or Anthropic)
   - Trading parameters

**Important:** Never commit `config.toml` to version control as it contains sensitive credentials.

## Usage

Run the agent with default configuration:

```bash
hyperliquid-agent
```

Run with custom configuration:

```bash
hyperliquid-agent --config path/to/config.toml
```

## Development

### Requirements

- Python 3.11 or later
- uv package manager

### Setup Development Environment

Install with dev dependencies:

```bash
uv sync --extra dev
```

### Code Quality

Format code:

```bash
uv run ruff format src/
```

Lint code:

```bash
uv run ruff check src/
```

Type check:

```bash
uv run pyrefly check src/
```

### Testing

Run tests:

```bash
uv run pytest
```

## Safety

- Always test on Hyperliquid testnet first
- Monitor the agent's behavior closely
- Set appropriate position limits
- Keep API keys secure

## License

MIT
