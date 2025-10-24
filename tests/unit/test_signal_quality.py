"""Unit tests for signal quality metadata and confidence scoring."""

from datetime import datetime

import pytest

from hyperliquid_agent.signals.models import SignalQualityMetadata

# ============================================================================
# SignalQualityMetadata Tests
# ============================================================================


def test_signal_quality_metadata_creation():
    """Test basic SignalQualityMetadata creation."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.95,
        staleness_seconds=10.0,
        sources=["hyperliquid", "coingecko"],
        is_cached=False,
    )

    assert metadata.confidence == 0.95
    assert metadata.staleness_seconds == 10.0
    assert len(metadata.sources) == 2
    assert metadata.is_cached is False


def test_signal_quality_create_fresh():
    """Test creating fresh signal metadata."""
    sources = ["hyperliquid", "external"]
    metadata = SignalQualityMetadata.create_fresh(sources)

    assert metadata.confidence == 1.0
    assert metadata.staleness_seconds == 0.0
    assert metadata.sources == sources
    assert metadata.is_cached is False
    assert isinstance(metadata.timestamp, datetime)


def test_signal_quality_create_cached():
    """Test creating cached signal metadata."""
    sources = ["hyperliquid"]
    cache_age = 30.0  # 30 seconds old

    metadata = SignalQualityMetadata.create_cached(sources, cache_age)

    assert metadata.staleness_seconds == cache_age
    assert metadata.sources == sources
    assert metadata.is_cached is True
    assert 0.0 <= metadata.confidence <= 1.0


def test_signal_quality_create_fallback():
    """Test creating fallback signal metadata."""
    metadata = SignalQualityMetadata.create_fallback()

    assert metadata.confidence == 0.0
    assert metadata.staleness_seconds == float("inf")
    assert metadata.sources == []
    assert metadata.is_cached is False


def test_calculate_confidence_fresh_complete_data():
    """Test confidence calculation with fresh, complete data."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,  # Will be calculated
        staleness_seconds=0.0,
        sources=["source1", "source2"],
        is_cached=False,
    )

    expected_sources = ["source1", "source2"]
    confidence = metadata.calculate_confidence(expected_sources)

    # Fresh data with all sources should have confidence 1.0
    assert confidence == 1.0


def test_calculate_confidence_missing_sources():
    """Test confidence calculation with missing sources."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=0.0,
        sources=["source1"],  # Only 1 of 2 expected
        is_cached=False,
    )

    expected_sources = ["source1", "source2"]
    confidence = metadata.calculate_confidence(expected_sources)

    # Should be penalized for missing source: 0.5 * 1.0 = 0.5
    assert confidence == pytest.approx(0.5)


def test_calculate_confidence_stale_data():
    """Test confidence calculation with stale data."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=700.0,  # 11+ minutes old
        sources=["source1"],
        is_cached=True,
    )

    expected_sources = ["source1"]
    confidence = metadata.calculate_confidence(expected_sources, max_staleness_seconds=600.0)

    # Data older than max_staleness gets penalty: 600/700 = 0.857
    assert confidence == pytest.approx(0.857, abs=0.01)


def test_calculate_confidence_moderately_stale():
    """Test confidence calculation with moderately stale data."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=300.0,  # 5 minutes old
        sources=["source1"],
        is_cached=True,
    )

    expected_sources = ["source1"]
    confidence = metadata.calculate_confidence(expected_sources, max_staleness_seconds=600.0)

    # Should be between 0.5 and 1.0 (linear decay)
    assert 0.5 < confidence < 1.0


def test_calculate_confidence_combined_penalties():
    """Test confidence calculation with both missing sources and staleness."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=300.0,  # 5 minutes old
        sources=["source1"],  # Only 1 of 2 expected
        is_cached=True,
    )

    expected_sources = ["source1", "source2"]
    confidence = metadata.calculate_confidence(expected_sources, max_staleness_seconds=600.0)

    # Should be penalized for both: 0.5 (missing source) * ~0.75 (staleness) = ~0.375
    assert 0.3 < confidence < 0.5


def test_calculate_confidence_no_expected_sources():
    """Test confidence calculation without expected sources."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=100.0,
        sources=["source1"],
        is_cached=True,
    )

    # Without expected sources, only staleness matters
    confidence = metadata.calculate_confidence([], max_staleness_seconds=600.0)

    assert 0.5 < confidence < 1.0


def test_calculate_confidence_clamping():
    """Test that confidence is clamped to [0, 1]."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=0.0,
        sources=["s1", "s2", "s3"],  # More sources than expected
        is_cached=False,
    )

    expected_sources = ["s1"]
    confidence = metadata.calculate_confidence(expected_sources)

    # Should be clamped to 1.0 even with extra sources
    assert confidence <= 1.0


def test_calculate_confidence_zero_staleness():
    """Test confidence with zero staleness."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=0.0,
        sources=["source1"],
        is_cached=False,
    )

    expected_sources = ["source1"]
    confidence = metadata.calculate_confidence(expected_sources)

    # Zero staleness with complete sources should be 1.0
    assert confidence == 1.0


def test_calculate_confidence_at_max_staleness():
    """Test confidence exactly at max staleness threshold."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=600.0,  # Exactly at threshold
        sources=["source1"],
        is_cached=True,
    )

    expected_sources = ["source1"]
    confidence = metadata.calculate_confidence(expected_sources, max_staleness_seconds=600.0)

    # At threshold, confidence should be 0.5
    assert confidence == pytest.approx(0.5)


def test_calculate_confidence_custom_max_staleness():
    """Test confidence calculation with custom max staleness."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=1800.0,  # 30 minutes
        sources=["source1"],
        is_cached=True,
    )

    expected_sources = ["source1"]

    # With 30-minute threshold, should be at 0.5
    confidence = metadata.calculate_confidence(expected_sources, max_staleness_seconds=1800.0)
    assert confidence == pytest.approx(0.5)

    # With 10-minute threshold, should be much lower
    confidence = metadata.calculate_confidence(expected_sources, max_staleness_seconds=600.0)
    assert confidence < 0.5


def test_create_cached_with_expected_sources():
    """Test create_cached with expected sources for confidence calculation."""
    sources = ["source1"]
    expected_sources = ["source1", "source2"]
    cache_age = 300.0

    metadata = SignalQualityMetadata.create_cached(sources, cache_age, expected_sources)

    # Should have calculated confidence based on missing source and staleness
    assert 0.0 < metadata.confidence < 1.0
    assert metadata.is_cached is True


def test_create_cached_without_expected_sources():
    """Test create_cached without expected sources."""
    sources = ["source1"]
    cache_age = 100.0

    metadata = SignalQualityMetadata.create_cached(sources, cache_age)

    # Should have calculated confidence based only on staleness
    assert 0.0 < metadata.confidence < 1.0
    assert metadata.is_cached is True


def test_signal_quality_metadata_immutability():
    """Test that metadata fields can be accessed correctly."""
    metadata = SignalQualityMetadata.create_fresh(["source1"])

    # Should be able to read all fields
    assert isinstance(metadata.timestamp, datetime)
    assert isinstance(metadata.confidence, float)
    assert isinstance(metadata.staleness_seconds, float)
    assert isinstance(metadata.sources, list)
    assert isinstance(metadata.is_cached, bool)


def test_confidence_linear_decay():
    """Test that confidence decays linearly from 1.0 to 0.5 within max_staleness."""
    expected_sources = ["source1"]

    # Test at various points in the decay curve
    test_points = [
        (0.0, 1.0),  # Fresh data
        (150.0, 0.875),  # 25% of max_staleness
        (300.0, 0.75),  # 50% of max_staleness
        (450.0, 0.625),  # 75% of max_staleness
        (600.0, 0.5),  # At max_staleness
    ]

    for staleness, expected_confidence in test_points:
        metadata = SignalQualityMetadata(
            timestamp=datetime.now(),
            confidence=0.0,
            staleness_seconds=staleness,
            sources=["source1"],
            is_cached=True,
        )

        confidence = metadata.calculate_confidence(expected_sources, max_staleness_seconds=600.0)
        assert confidence == pytest.approx(expected_confidence, abs=0.01)


def test_confidence_beyond_max_staleness():
    """Test confidence calculation beyond max staleness threshold."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=1200.0,  # 2x max_staleness
        sources=["source1"],
        is_cached=True,
    )

    expected_sources = ["source1"]
    confidence = metadata.calculate_confidence(expected_sources, max_staleness_seconds=600.0)

    # Should be 1.0 * (600/1200) = 0.5
    assert confidence == pytest.approx(0.5, abs=0.01)


def test_confidence_with_empty_sources():
    """Test confidence calculation with empty sources list."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=0.0,
        sources=[],
        is_cached=False,
    )

    expected_sources = ["source1", "source2"]
    confidence = metadata.calculate_confidence(expected_sources)

    # No sources provided, should be 0.0
    assert confidence == 0.0


def test_confidence_with_extra_sources():
    """Test confidence calculation with more sources than expected."""
    metadata = SignalQualityMetadata(
        timestamp=datetime.now(),
        confidence=0.0,
        staleness_seconds=0.0,
        sources=["source1", "source2", "source3"],
        is_cached=False,
    )

    expected_sources = ["source1", "source2"]
    confidence = metadata.calculate_confidence(expected_sources)

    # Extra sources shouldn't hurt: 3/2 = 1.5, but clamped to 1.0
    assert confidence == 1.0
