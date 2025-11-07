# Deployment Guide

This guide covers deploying the Hyperliquid Trading Agent to production environments, including Docker containerization, environment configuration, logging setup, disaster recovery, and performance tuning.

## Docker Deployment

### Dockerfile

Create a `Dockerfile` in your project root:

```dockerfile
# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY strategies/ ./strategies/

# Install dependencies
RUN uv pip install --system -e .

# Create directories for logs and state
RUN mkdir -p /app/logs /app/state /app/backtest_results

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the agent
CMD ["python", "-m", "hyperliquid_agent.cli", "start", "--config", "/app/config.toml"]
```

### Docker Compose Setup

Create a `docker-compose.yml` for easier management:

```yaml
version: '3.8'

services:
  trading-agent:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: hyperliquid-agent
    restart: unless-stopped
    
    # Mount configuration and persistent data
    volumes:
      - ./config.toml:/app/config.toml:ro
      - ./logs:/app/logs
      - ./state:/app/state
      - ./backtest_results:/app/backtest_results
    
    # Environment variables (override config.toml)
    environment:
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - HYPERLIQUID_ACCOUNT_ADDRESS=${HYPERLIQUID_ACCOUNT_ADDRESS}
      - HYPERLIQUID_SECRET_KEY=${HYPERLIQUID_SECRET_KEY}
      - HYPERLIQUID_BASE_URL=${HYPERLIQUID_BASE_URL:-https://api.hyperliquid-testnet.xyz}
      - LLM_PROVIDER=${LLM_PROVIDER:-openai}
      - LLM_MODEL=${LLM_MODEL:-gpt-4}
      - LLM_API_KEY=${LLM_API_KEY}
      - ONCHAIN_API_KEY=${ONCHAIN_API_KEY}
      - COINGECKO_API_KEY=${COINGECKO_API_KEY}
    
    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
    
    # Logging configuration
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    
    # Network configuration
    networks:
      - trading-network

  # Optional: Add monitoring with Prometheus
  # prometheus:
  #   image: prom/prometheus:latest
  #   container_name: prometheus
  #   volumes:
  #     - ./prometheus.yml:/etc/prometheus/prometheus.yml
  #     - prometheus-data:/prometheus
  #   ports:
  #     - "9090:9090"
  #   networks:
  #     - trading-network

networks:
  trading-network:
    driver: bridge

volumes:
  prometheus-data:
```

### Deployment Commands

**Build the Docker image:**

```bash
docker build -t hyperliquid-agent:latest .
```

**Run with Docker Compose:**

```bash
# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f trading-agent

# Stop the agent
docker-compose down

# Restart the agent
docker-compose restart trading-agent
```

**Run standalone Docker container:**

```bash
docker run -d \
  --name hyperliquid-agent \
  --restart unless-stopped \
  -v $(pwd)/config.toml:/app/config.toml:ro \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/state:/app/state \
  -e LOG_LEVEL=INFO \
  hyperliquid-agent:latest
```

### Multi-Stage Build (Optimized)

For production, use a multi-stage build to reduce image size:

```dockerfile
# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN uv pip install --system -e .

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY strategies/ ./strategies/

# Create directories
RUN mkdir -p /app/logs /app/state

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "hyperliquid_agent.cli", "start"]
```

## Environment Variables

Environment variables take precedence over `config.toml` settings, making them ideal for containerized deployments and CI/CD pipelines.

### Supported Environment Variables

#### Hyperliquid Configuration

```bash
# Account credentials
HYPERLIQUID_ACCOUNT_ADDRESS="0x..."
HYPERLIQUID_SECRET_KEY="0x..."
HYPERLIQUID_BASE_URL="https://api.hyperliquid-testnet.xyz"
```

#### LLM Configuration

```bash
# LLM provider settings
LLM_PROVIDER="openai"  # or "anthropic"
LLM_MODEL="gpt-4"
LLM_API_KEY="sk-..."
LLM_TEMPERATURE="0.7"
LLM_MAX_TOKENS="1000"
```

#### Agent Configuration

```bash
# Agent behavior
LOG_LEVEL="INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
TICK_INTERVAL_SECONDS="60"
MAX_RETRIES="5"
RETRY_BACKOFF_BASE="2.0"
PROMPT_TEMPLATE_PATH="prompts/default.txt"
```

#### Signal System Configuration

```bash
# On-chain data providers
ONCHAIN_API_KEY="..."  # For token unlocks, Nansen, Dune

# External market data
COINGECKO_API_KEY="..."  # Optional, for higher rate limits
JBLANKED_API_KEY="..."   # Optional

# Sentiment data
# Fear & Greed Index is free, no API key needed
```

### Configuration Precedence

The agent loads configuration in this order (later sources override earlier ones):

1. Default values in code
2. `config.toml` file
3. Environment variables

**Example:**

```toml
# config.toml
[agent]
log_level = "INFO"
```

```bash
# Override with environment variable
export LOG_LEVEL="DEBUG"

# Now the agent will use DEBUG level
```

### Using .env Files

Create a `.env` file for local development:

```bash
# .env
HYPERLIQUID_ACCOUNT_ADDRESS=0x...
HYPERLIQUID_SECRET_KEY=0x...
HYPERLIQUID_BASE_URL=https://api.hyperliquid-testnet.xyz

LLM_PROVIDER=openai
LLM_MODEL=gpt-4
LLM_API_KEY=sk-...

LOG_LEVEL=INFO
```

**Load with Docker Compose:**

```yaml
services:
  trading-agent:
    env_file:
      - .env
```

**Load in shell:**

```bash
# Export all variables from .env
export $(cat .env | xargs)

# Run the agent
python -m hyperliquid_agent.cli start
```

### Security Best Practices

**Never commit secrets to version control:**

```bash
# Add to .gitignore
echo ".env" >> .gitignore
echo "config.toml" >> .gitignore
```

**Use secret management services in production:**

- AWS Secrets Manager
- HashiCorp Vault
- Kubernetes Secrets
- Docker Secrets

**Example with Docker Secrets:**

```yaml
services:
  trading-agent:
    secrets:
      - hyperliquid_secret_key
      - llm_api_key
    environment:
      - HYPERLIQUID_SECRET_KEY_FILE=/run/secrets/hyperliquid_secret_key
      - LLM_API_KEY_FILE=/run/secrets/llm_api_key

secrets:
  hyperliquid_secret_key:
    external: true
  llm_api_key:
    external: true
```

## Logging and Observability

The agent uses Python's standard logging module with structured output for production monitoring.

### Log Format

Logs are written in a structured format to both console and file:

**Console output (human-readable):**

```
2025-11-05 10:30:00 - INFO - Starting trading agent
2025-11-05 10:30:01 - INFO - Account state retrieved: portfolio_value=$10000.00
2025-11-05 10:30:03 - INFO - Decision received: 1 actions, strategy=funding-harvest-lite
2025-11-05 10:30:04 - INFO - Trade executed: buy BTC perp, success=True
```

**File output (JSON for parsing):**

```json
{
  "timestamp": "2025-11-05T10:30:00.123Z",
  "level": "INFO",
  "message": "Trade executed",
  "action": "buy",
  "coin": "BTC",
  "market_type": "perp",
  "success": true,
  "order_id": "0x..."
}
```

### Log Levels

Configure logging verbosity with the `LOG_LEVEL` environment variable:

- **DEBUG**: Detailed diagnostic information (API calls, market data, calculations)
- **INFO**: General informational messages (trades, decisions, status updates)
- **WARNING**: Warning messages (retries, degraded performance, non-critical errors)
- **ERROR**: Error messages (failed trades, API errors, configuration issues)
- **CRITICAL**: Critical errors (system failures, emergency shutdowns)

**Production recommendation:** Use `INFO` for normal operation, `DEBUG` for troubleshooting.

### Log Files

Logs are written to `logs/agent.log` by default:

```bash
# View live logs
tail -f logs/agent.log

# Search for errors
grep ERROR logs/agent.log

# View last 100 lines
tail -n 100 logs/agent.log
```

### Log Rotation

Configure log rotation to prevent disk space issues:

**Using logrotate (Linux):**

Create `/etc/logrotate.d/hyperliquid-agent`:

```
/path/to/hyperliquid-trading-agent/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 user group
}
```

**Using Docker logging driver:**

```yaml
services:
  trading-agent:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Monitoring Setup

**Prometheus Metrics (Future Enhancement):**

The agent can be extended to expose Prometheus metrics:

```python
# Example metrics to track
- trading_decisions_total
- trades_executed_total
- trades_failed_total
- portfolio_value_usd
- api_request_duration_seconds
- llm_token_usage_total
```

**Grafana Dashboard:**

Create dashboards to visualize:
- Portfolio value over time
- Trade success rate
- API latency
- LLM costs
- Error rates

**Alerting:**

Set up alerts for:
- Failed trades
- API errors
- Portfolio drawdown
- High LLM costs
- System errors

### Centralized Logging

**Send logs to external services:**

**Elasticsearch/Logstash/Kibana (ELK):**

```yaml
services:
  trading-agent:
    logging:
      driver: "gelf"
      options:
        gelf-address: "udp://logstash:12201"
```

**CloudWatch Logs (AWS):**

```yaml
services:
  trading-agent:
    logging:
      driver: "awslogs"
      options:
        awslogs-region: "us-east-1"
        awslogs-group: "hyperliquid-agent"
        awslogs-stream: "production"
```

## Disaster Recovery

### State Backup and Restore

The agent maintains state in the `state/` directory:

```
state/
├── governor.json          # Governance system state
└── signal_cache.db        # Signal cache database
```

**Backup strategy:**

```bash
#!/bin/bash
# backup.sh - Run daily via cron

BACKUP_DIR="/backups/hyperliquid-agent"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup state files
tar -czf "$BACKUP_DIR/state_$DATE.tar.gz" state/

# Backup configuration
cp config.toml "$BACKUP_DIR/config_$DATE.toml"

# Backup logs
tar -czf "$BACKUP_DIR/logs_$DATE.tar.gz" logs/

# Keep only last 7 days of backups
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.toml" -mtime +7 -delete

echo "Backup completed: $DATE"
```

**Automated backups with cron:**

```bash
# Run backup daily at 2 AM
0 2 * * * /path/to/backup.sh >> /var/log/hyperliquid-backup.log 2>&1
```

**Restore from backup:**

```bash
# Stop the agent
docker-compose down

# Restore state
tar -xzf /backups/hyperliquid-agent/state_20251105_020000.tar.gz

# Restore configuration
cp /backups/hyperliquid-agent/config_20251105_020000.toml config.toml

# Restart the agent
docker-compose up -d
```

### Emergency Shutdown

**Graceful shutdown:**

```bash
# Send SIGTERM to allow cleanup
docker-compose stop

# Or with Docker
docker stop hyperliquid-agent
```

**Force shutdown:**

```bash
# Send SIGKILL (last resort)
docker-compose kill

# Or with Docker
docker kill hyperliquid-agent
```

**Emergency position closure:**

If you need to immediately close all positions:

```bash
# Use the CLI to check positions
docker-compose exec trading-agent python -m hyperliquid_agent.cli status

# Manually close positions via Hyperliquid UI
# https://app.hyperliquid.xyz/
```

### Recovery Procedures

**Scenario 1: Agent crashes**

```bash
# Check logs for errors
docker-compose logs --tail=100 trading-agent

# Restart the agent
docker-compose restart trading-agent

# Verify it's running
docker-compose ps
```

**Scenario 2: Corrupted state**

```bash
# Stop the agent
docker-compose down

# Restore from backup
tar -xzf /backups/hyperliquid-agent/state_LATEST.tar.gz

# Or start fresh (loses governance history)
rm -rf state/
mkdir state/

# Restart
docker-compose up -d
```

**Scenario 3: Configuration error**

```bash
# Validate configuration
docker-compose exec trading-agent python -c "
from hyperliquid_agent.config import load_config
try:
    config = load_config('config.toml')
    print('Configuration valid')
except Exception as e:
    print(f'Configuration error: {e}')
"

# Fix configuration and restart
docker-compose restart trading-agent
```

**Scenario 4: API connectivity issues**

```bash
# Test Hyperliquid API
curl https://api.hyperliquid-testnet.xyz/info

# Test LLM API
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $LLM_API_KEY"

# Check network connectivity from container
docker-compose exec trading-agent ping -c 3 api.hyperliquid.xyz
```

### Disaster Recovery Checklist

1. **Stop the agent** to prevent further trades
2. **Assess the situation** by reviewing logs
3. **Check positions** on Hyperliquid UI
4. **Restore from backup** if state is corrupted
5. **Fix the root cause** (config, network, API keys)
6. **Test in testnet** before restarting in production
7. **Monitor closely** after recovery
8. **Document the incident** for future reference

## Performance Tuning

### Signal Cache Optimization

The signal cache reduces API calls and improves performance. Tune TTL values based on your trading frequency:

**Conservative (hobby trading):**

```toml
[signals.onchain]
cache_ttl_seconds = 3600  # 1 hour

[signals.external_market]
cache_ttl_seconds = 900   # 15 minutes

[signals.sentiment]
cache_ttl_seconds = 1800  # 30 minutes

[signals.computed]
cache_ttl_seconds = 300   # 5 minutes
```

**Aggressive (active trading):**

```toml
[signals.onchain]
cache_ttl_seconds = 1800  # 30 minutes

[signals.external_market]
cache_ttl_seconds = 300   # 5 minutes

[signals.sentiment]
cache_ttl_seconds = 600   # 10 minutes

[signals.computed]
cache_ttl_seconds = 60    # 1 minute
```

**Cache maintenance:**

```bash
# Check cache size
du -sh state/signal_cache.db

# Vacuum database to reclaim space
sqlite3 state/signal_cache.db "VACUUM;"

# Clear cache (forces fresh data)
rm state/signal_cache.db
```

### Concurrent Request Tuning

The signal system uses async concurrent requests. Tune based on your network and API rate limits:

```toml
[signals]
timeout_seconds = 30.0  # Increase if requests timeout

[signals.hyperliquid]
max_retries = 3         # Increase for unreliable networks
timeout_seconds = 10.0  # Increase for slow connections
backoff_factor = 2.0    # Exponential backoff multiplier
```

**Monitoring concurrent requests:**

```bash
# Enable DEBUG logging to see request timing
export LOG_LEVEL=DEBUG

# Look for these log messages:
# - "Signal collection started"
# - "Signal collection completed in X.XXs"
# - "Provider X timed out"
```

### Resource Allocation

**CPU allocation:**

- **Minimum:** 1 CPU core
- **Recommended:** 2 CPU cores
- **Optimal:** 4 CPU cores for governed mode with async loops

**Memory allocation:**

- **Minimum:** 512 MB
- **Recommended:** 1 GB
- **Optimal:** 2 GB for signal caching and backtesting

**Disk space:**

- **Logs:** 100 MB - 1 GB (with rotation)
- **State:** 10 MB - 100 MB
- **Cache:** 50 MB - 500 MB
- **Total recommended:** 5 GB

**Docker resource limits:**

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
    reservations:
      cpus: '1'
      memory: 1G
```

### Network Optimization

**Reduce API calls:**

1. **Increase tick interval** for less frequent trading:

```toml
[agent]
tick_interval_seconds = 300  # 5 minutes instead of 60 seconds
```

2. **Enable caching** for all signal providers:

```toml
[signals]
caching_enabled = true
```

3. **Use governed mode** to reduce LLM queries:

```bash
# LLM queries only during medium loop (every 30 minutes)
# instead of every tick (every 60 seconds)
docker-compose exec trading-agent python -m hyperliquid_agent.cli start --governed
```

### Performance Metrics to Track

**Latency metrics:**

- Signal collection time (target: < 5 seconds)
- LLM decision time (target: < 10 seconds)
- Trade execution time (target: < 2 seconds)
- Total tick time (target: < 20 seconds)

**Throughput metrics:**

- Ticks per hour
- Trades per day
- API calls per minute
- LLM tokens per day

**Resource metrics:**

- CPU usage (target: < 50% average)
- Memory usage (target: < 1 GB)
- Disk I/O (target: < 10 MB/s)
- Network bandwidth (target: < 1 Mbps)

**Cost metrics:**

- LLM API costs per day
- Exchange fees per trade
- Infrastructure costs (hosting, monitoring)

### Load Testing

Test the agent's performance under load:

```bash
# Run backtest with high frequency
python -m hyperliquid_agent.backtesting.cli backtest \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --tick-interval 60

# Monitor resource usage
docker stats hyperliquid-agent

# Check for bottlenecks in logs
grep "timeout\|slow\|retry" logs/agent.log
```

### Optimization Checklist

- [ ] Enable signal caching
- [ ] Tune cache TTL values for your trading frequency
- [ ] Set appropriate resource limits
- [ ] Configure log rotation
- [ ] Use governed mode to reduce LLM queries
- [ ] Monitor latency and throughput metrics
- [ ] Optimize network calls with batching
- [ ] Use async mode for concurrent execution
- [ ] Set up alerting for performance degradation
- [ ] Regularly vacuum SQLite cache database

## Production Deployment Checklist

Before deploying to production:

- [ ] Test thoroughly on testnet
- [ ] Configure proper resource limits
- [ ] Set up log rotation
- [ ] Configure automated backups
- [ ] Set up monitoring and alerting
- [ ] Document recovery procedures
- [ ] Use environment variables for secrets
- [ ] Enable health checks
- [ ] Test disaster recovery procedures
- [ ] Start with small capital
- [ ] Monitor actively for first 24 hours
- [ ] Have emergency shutdown procedure ready

## Next Steps

- [Configuration Reference](./configuration.md) - Detailed configuration options
- [Troubleshooting Guide](./troubleshooting.md) - Common issues and solutions
- [Architecture Overview](../architecture/overview.md) - System architecture
- [Performance Tuning](../architecture/performance.md) - Advanced optimization
