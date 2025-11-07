# Macro Economic Calendar Setup

The trading agent uses macro economic calendar data (FOMC meetings, CPI releases, NFP reports, etc.) to inform regime detection and trading decisions.

## Data Source

The macro calendar is fetched from **JBlanked API**, which aggregates economic calendar data from multiple sources including Forex Factory and MQL5.

## Setup Instructions

### 1. Get a Free API Key

1. Visit [JBlanked](https://www.jblanked.com/)
2. Create an account
3. Navigate to your [Profile](https://www.jblanked.com/profile/) to generate an API key
4. Note: Free tier allows 1 request per day, which is sufficient since the slow loop runs once per 24 hours

### 2. Configure the API Key

**Option 1: Add to config.toml (Recommended)**

Edit your `config.toml` file and add the API key:

```toml
[signals.external_market]
enabled = true
use_coingecko = true
use_yfinance = true
jblanked_api_key = "your_api_key_here"
cache_ttl_seconds = 900
```

**Option 2: Environment Variable**

Set the API key as an environment variable:

```bash
export JBLANKED_API_KEY="your_api_key_here"
```

Or add it to your `.env` file:

```
JBLANKED_API_KEY=your_api_key_here
```

Note: Environment variables take precedence over config.toml values.

### 3. Verify Integration

The agent will automatically fetch macro events when the slow loop runs. Check the logs for:

```
INFO Fetched X macro events from JBlanked API within 7 days
```

## Fallback Mechanism

If the API is unavailable or no API key is configured, the system falls back to a local JSON file at `data/macro_calendar.json`. This file contains sample events and can be manually updated if needed.

## API Details

- **Endpoint**: `https://www.jblanked.com/news/api/mql5/calendar/upcoming/`
- **Rate Limit**: 1 request per day (free tier)
- **Cache TTL**: 15 minutes (configured in `ExternalMarketProvider`)
- **Documentation**: [JBlanked Calendar API Docs](https://www.jblanked.com/news/api/docs/calendar/)

## Event Filtering

The system automatically:
- Filters for high-impact USD events (FOMC, CPI, NFP, GDP, Interest Rate decisions)
- Filters events within the requested time window (default: 7 days ahead)
- Parses event dates and converts to UTC
- Creates `MacroEvent` objects with name, datetime, impact level, and category

## Monitoring API Usage

You can monitor your API usage at: https://www.jblanked.com/api/usage/

## Troubleshooting

### No events appearing in logs

1. Check that `JBLANKED_API_KEY` environment variable is set
2. Verify the API key is valid at https://www.jblanked.com/profile/
3. Check if you've exceeded the daily rate limit
4. Look for error messages in logs: `Failed to fetch macro calendar from API`

### Fallback to file-based calendar

If you see `Loaded X macro events from fallback file`, it means:
- No API key is configured, OR
- The API request failed

This is expected behavior and the system will continue to work with the local calendar file.

## Example Response

The API returns events in this format:

```json
{
  "Name": "Core CPI m/m",
  "Currency": "USD",
  "Category": "Consumer Inflation Report",
  "Date": "2024.02.08 15:30:00",
  "Actual": 0.4,
  "Forecast": 0.4,
  "Previous": 0.2
}
```

The system extracts the relevant fields and creates `MacroEvent` objects for use in regime detection.
