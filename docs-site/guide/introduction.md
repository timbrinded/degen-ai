# Introduction

## What is Hyperliquid Trading Agent?

The Hyperliquid Trading Agent is an autonomous AI-powered trading system designed for Hyperliquid perpetual futures markets. It combines multiple data sources, sophisticated signal processing, and LLM-based decision making to execute trading strategies.

## Key Features

### Multi-Strategy Governance
- Dynamic strategy selection based on market regimes
- Performance tracking and scorekeeper system
- Automatic strategy rotation and portfolio rebalancing

### Comprehensive Signal System
- **On-chain metrics**: Funding rates, open interest, liquidations
- **Market data**: Price action, volume, volatility
- **Sentiment analysis**: Social media and news sentiment
- **External markets**: Correlation with traditional assets

### Risk Management
- Tripwire system for automatic position management
- Portfolio-level risk controls
- Per-strategy performance monitoring

## How It Works

1. **Signal Collection**: Aggregates real-time data from multiple providers
2. **Regime Detection**: Classifies current market conditions
3. **Strategy Selection**: Chooses optimal strategies for the regime
4. **Decision Making**: LLM analyzes signals and generates trading decisions
5. **Execution**: Places orders on Hyperliquid with proper risk management
6. **Monitoring**: Tracks performance and adjusts strategy allocation

## Use Cases

- Automated perpetual futures trading
- Multi-strategy portfolio management
- Market regime-based strategy rotation
- Funding rate arbitrage
- Trend following and mean reversion
