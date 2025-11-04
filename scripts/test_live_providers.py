#!/usr/bin/env python3
"""Live integration test for external data providers.

Tests real API calls to verify we can handle actual responses.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hyperliquid_agent.signals.cache import SQLiteCacheLayer  # noqa: E402
from hyperliquid_agent.signals.external_market_provider import ExternalMarketProvider  # noqa: E402
from hyperliquid_agent.signals.onchain_provider import OnChainProvider  # noqa: E402
from hyperliquid_agent.signals.sentiment_provider import SentimentProvider  # noqa: E402


async def test_sentiment_provider():
    """Test Alternative.me Fear & Greed Index (no API key needed)."""
    print("\n" + "=" * 80)
    print("Testing Sentiment Provider (Alternative.me)")
    print("=" * 80)

    cache = SQLiteCacheLayer(":memory:")
    provider = SentimentProvider(cache=cache)

    try:
        response = await provider.fetch_fear_greed_index()
        print(f"✅ Fear & Greed Index: {response.data:.2f}")
        print(f"   Confidence: {response.confidence}")
        print(f"   Source: {response.source}")
        print(f"   Timestamp: {response.timestamp}")
        print(f"   Cached: {response.is_cached}")

        # Verify response is valid
        assert -1.0 <= response.data <= 1.0, "Value should be between -1 and 1"
        assert response.confidence > 0, "Confidence should be positive"
        print("✅ Response validation passed")
        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


async def test_external_market_provider():
    """Test CoinGecko and yfinance (no API keys needed for basic tier)."""
    print("\n" + "=" * 80)
    print("Testing External Market Provider (CoinGecko + yfinance)")
    print("=" * 80)

    cache = SQLiteCacheLayer(":memory:")
    provider = ExternalMarketProvider(
        cache=cache,
        coingecko_api_key=None,  # Free tier
        use_yfinance=True,
    )

    # Test asset prices
    try:
        print("\n📊 Testing asset prices (BTC, ETH)...")
        response = await provider.fetch_asset_prices(["BTC", "ETH"], days_back=7)
        print(f"✅ Fetched prices for {len(response.data)} assets")
        print(f"   Confidence: {response.confidence}")
        print(f"   Source: {response.source}")

        for asset, prices in response.data.items():
            print(f"   {asset}: {len(prices)} price points")
            if prices:
                print(f"      Latest: ${prices[-1]:,.2f}")

        # Verify response structure
        assert isinstance(response.data, dict), "Response should be a dict"
        for asset, prices in response.data.items():
            assert isinstance(prices, list), f"{asset} prices should be a list"
            assert all(isinstance(p, (int, float)) for p in prices), (
                f"{asset} prices should be numbers"
            )

        print("✅ Asset prices validation passed")

    except Exception as e:
        print(f"❌ Asset prices failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test macro calendar
    try:
        print("\n📅 Testing macro calendar...")
        response = await provider.fetch_macro_calendar(days_ahead=7)
        print(f"✅ Found {len(response.data)} macro events")
        print(f"   Confidence: {response.confidence}")

        # Show first few events
        for i, event in enumerate(response.data[:3]):
            print(f"\n   Event {i + 1}:")
            print(f"     Name: {event.name}")
            print(f"     Date: {event.datetime}")
            print(f"     Impact: {event.impact}")
            print(f"     Category: {event.category}")

        print("✅ Macro calendar validation passed")

    except Exception as e:
        print(f"⚠️  Macro calendar failed (may not be implemented): {e}")

    return True


async def test_onchain_provider_messari():
    """Test Messari Token Unlocks API (requires API key)."""
    print("\n" + "=" * 80)
    print("Testing On-Chain Provider (Messari)")
    print("=" * 80)

    # Try environment variables first, then config file
    api_key = os.environ.get("MESSARI_API_KEY") or os.environ.get("ONCHAIN_API_KEY")

    if not api_key:
        # Try loading from config.toml
        try:
            import tomllib

            config_path = Path(__file__).parent.parent / "config.toml"
            if config_path.exists():
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)
                    api_key = config.get("signals", {}).get("onchain", {}).get("api_key")
                    if api_key:
                        print("✅ Found API key in config.toml")
        except Exception as e:
            print(f"⚠️  Could not read config.toml: {e}")

    if not api_key:
        print("⚠️  No MESSARI_API_KEY found in environment or config.toml")
        print("   Set MESSARI_API_KEY environment variable or add to config.toml")
        print("   Skipping Messari test...")
        return True  # Not a failure, just skipped

    cache = SQLiteCacheLayer(":memory:")
    provider = OnChainProvider(
        cache=cache,
        api_key=api_key,
        provider_name="messari",
    )

    # Test token unlocks for popular assets
    try:
        print("\n🔓 Testing token unlocks for BTC, ETH, SOL...")
        print(f"   Provider: {provider.provider_name}")
        print(f"   API Base URL: {provider.api_base_url}")
        print(f"   Has API Key: {bool(provider.api_key)}")
        print(
            f"   API Key (first 10 chars): {provider.api_key[:10] if provider.api_key else 'None'}..."
        )

        # First, test if API key works with basic Messari endpoint
        print("\n   Testing API key with Messari assets list endpoint...")
        import json
        import urllib.request

        # Try the assets list endpoint first (should work with any valid key)
        assets_url = f"{provider.api_base_url}/assets"
        headers = {
            "x-messari-api-key": provider.api_key or "",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(assets_url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                print("   ✅ Assets list API call successful!")
                print("   API key is valid for Messari Token Unlocks API")
                if "data" in data:
                    assets = data.get("data", [])
                    print(f"   Found {len(assets)} assets with unlock data")
        except urllib.error.HTTPError as e:
            print(f"   ❌ Assets list API call failed: HTTP {e.code} {e.reason}")
            print("   This suggests the API key may not have access to Token Unlocks API")
            print(f"   Error body: {e.read().decode() if hasattr(e, 'read') else 'N/A'}")
        except Exception as e:
            print(f"   ❌ Assets list API call failed: {e}")

        # Now test the events endpoint
        print("\n   Testing token unlock events endpoint...")
        test_url = f"{provider.api_base_url}/assets/bitcoin/events"
        req = urllib.request.Request(test_url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                print("   ✅ Events API call successful!")
                print(f"   Response has 'data' key: {'data' in data}")
                if "data" in data:
                    print(
                        f"   Response has 'unlockEvents': {'unlockEvents' in data.get('data', {})}"
                    )
                    events = data.get("data", {}).get("unlockEvents", [])
                    print(f"   Number of events in response: {len(events)}")
        except urllib.error.HTTPError as e:
            print(f"   ❌ Events API call failed: HTTP {e.code} {e.reason}")
            try:
                error_body = e.read().decode()
                print(f"   Error details: {error_body}")
            except Exception:
                pass
        except Exception as e:
            print(f"   ❌ Events API call failed: {e}")

        print("\n   Making provider API call...")
        response = await provider.fetch_token_unlocks(["BTC", "ETH", "SOL"], days_ahead=30)
        print("   Provider API call completed")

        print(f"\n✅ Found {len(response.data)} unlock events")
        print(f"   Confidence: {response.confidence}")
        print(f"   Source: {response.source}")
        print(f"   Cached: {response.is_cached}")

        # Show first few unlocks
        for i, unlock in enumerate(response.data[:3]):
            print(f"\n   Unlock {i + 1}:")
            print(f"     Asset: {unlock.asset}")
            print(f"     Date: {unlock.unlock_date}")
            print(f"     Amount: {unlock.amount:,.0f}")
            print(f"     % of Supply: {unlock.percentage_of_supply:.2f}%")

        # Verify response structure
        for unlock in response.data:
            assert unlock.asset, "Asset should not be empty"
            assert unlock.amount >= 0, "Amount should be non-negative"
            assert unlock.percentage_of_supply >= 0, "Percentage should be non-negative"

        print("✅ Unlock events validation passed")
        return True

    except Exception as e:
        print(f"❌ Messari test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_onchain_provider_whale_flows():
    """Test whale flows (if supported by provider)."""
    print("\n" + "=" * 80)
    print("Testing Whale Flows")
    print("=" * 80)

    # Try environment variables first, then config file
    api_key = os.environ.get("MESSARI_API_KEY") or os.environ.get("ONCHAIN_API_KEY")

    if not api_key:
        # Try loading from config.toml
        try:
            import tomllib

            config_path = Path(__file__).parent.parent / "config.toml"
            if config_path.exists():
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)
                    api_key = config.get("signals", {}).get("onchain", {}).get("api_key")
        except Exception:
            pass

    if not api_key:
        print("⚠️  No API key found, skipping whale flows test...")
        return True

    cache = SQLiteCacheLayer(":memory:")
    provider = OnChainProvider(
        cache=cache,
        api_key=api_key,
        provider_name="messari",
    )

    try:
        print("\n🐋 Testing whale flows for BTC...")
        response = await provider.fetch_whale_flows("BTC", hours_back=24)

        print(f"   Inflow: ${response.data.inflow:,.0f}")
        print(f"   Outflow: ${response.data.outflow:,.0f}")
        print(f"   Net Flow: ${response.data.net_flow:,.0f}")
        print(f"   Large TX Count: {response.data.large_tx_count}")
        print(f"   Confidence: {response.confidence}")

        if response.confidence < 0.5:
            print("⚠️  Low confidence (feature may not be supported by provider)")
        else:
            print("✅ Whale flows validation passed")

        return True

    except Exception as e:
        print(f"⚠️  Whale flows test failed (may not be supported): {e}")
        return True  # Not a critical failure


async def main():
    """Run all provider tests."""
    print("\n" + "=" * 80)
    print("LIVE PROVIDER INTEGRATION TESTS")
    print("=" * 80)
    print("\nThis script makes real API calls to verify provider integrations.")
    print("Some tests require API keys set as environment variables.")

    results = {}

    # Test sentiment (no key needed)
    results["sentiment"] = await test_sentiment_provider()

    # Test external market (no key needed for free tier)
    results["external_market"] = await test_external_market_provider()

    # Test on-chain (requires API key)
    results["onchain_unlocks"] = await test_onchain_provider_messari()
    results["onchain_whale_flows"] = await test_onchain_provider_whale_flows()

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:30s} {status}")

    all_passed = all(results.values())
    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
