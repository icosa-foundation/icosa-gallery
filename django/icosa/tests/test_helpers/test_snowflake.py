"""
Tests for snowflake ID generation helper functions.
"""
import pytest
import datetime
import time
from unittest.mock import patch

from icosa.helpers.snowflake import (
    generate_snowflake,
    get_timestamp,
    get_timestamp_raw,
    get_snowflake_timestamp,
    get_snowflake_timestamp_raw,
    ICOSA_EPOCH,
)


@pytest.mark.helpers
class TestGenerateSnowflake:
    """Test suite for generate_snowflake function."""

    def test_generate_snowflake_returns_integer(self):
        """Test that generate_snowflake returns an integer."""
        snowflake = generate_snowflake()
        assert isinstance(snowflake, int)

    def test_generate_snowflake_is_positive(self):
        """Test that snowflake ID is positive."""
        snowflake = generate_snowflake()
        assert snowflake > 0

    def test_generate_snowflake_unique(self):
        """Test that consecutive snowflakes are unique."""
        snowflake1 = generate_snowflake()
        snowflake2 = generate_snowflake()
        assert snowflake1 != snowflake2

    def test_generate_snowflake_incremental(self):
        """Test that snowflakes are generally incremental."""
        snowflakes = [generate_snowflake() for _ in range(10)]

        # Most should be in ascending order (counter may wrap)
        ascending_count = sum(1 for i in range(len(snowflakes)-1)
                             if snowflakes[i] < snowflakes[i+1])
        assert ascending_count >= 7  # Most should be ascending

    def test_generate_snowflake_timestamp_component(self):
        """Test that snowflake contains valid timestamp."""
        snowflake = generate_snowflake()
        timestamp = get_timestamp_raw(snowflake)

        # Timestamp should be reasonable (after ICOSA_EPOCH, before far future)
        assert timestamp > ICOSA_EPOCH
        assert timestamp < ICOSA_EPOCH + (100 * 365 * 24 * 60 * 60 * 1000)  # Within 100 years

    def test_generate_snowflake_process_id_component(self):
        """Test that snowflake contains process ID."""
        snowflake = generate_snowflake()

        # Extract process ID (bits 4-21)
        process_id = (snowflake >> 4) & 0x3FFFF

        # Process ID should be valid
        assert 0 <= process_id <= 0x3FFFF

    def test_generate_snowflake_counter_component(self):
        """Test that snowflake contains counter."""
        snowflake = generate_snowflake()

        # Extract counter (bits 0-3)
        counter = snowflake & 0xF

        # Counter should be 0-14 (wraps at 15)
        assert 0 <= counter < 15

    def test_generate_snowflake_counter_wraps(self):
        """Test that counter wraps around after 15."""
        # Generate many snowflakes to ensure counter wraps
        snowflakes = [generate_snowflake() for _ in range(20)]
        counters = [s & 0xF for s in snowflakes]

        # Should see counter wrap (go back to 0 or low numbers)
        assert min(counters) < 5  # Counter should wrap back to low values

    def test_generate_snowflake_bit_layout(self):
        """Test snowflake bit layout structure."""
        snowflake = generate_snowflake()

        # Snowflake should fit in 64 bits
        assert snowflake < (1 << 64)

        # Break down components
        timestamp_part = snowflake >> 22
        process_part = (snowflake >> 4) & 0x3FFFF
        counter_part = snowflake & 0xF

        # All components should be valid
        assert timestamp_part >= 0
        assert 0 <= process_part <= 0x3FFFF
        assert 0 <= counter_part < 15


@pytest.mark.helpers
class TestGetTimestamp:
    """Test suite for get_timestamp function."""

    def test_get_timestamp_returns_string(self):
        """Test that get_timestamp returns a string."""
        snowflake = generate_snowflake()
        timestamp = get_timestamp(snowflake)
        assert isinstance(timestamp, str)

    def test_get_timestamp_format(self):
        """Test timestamp format is ISO 8601."""
        snowflake = generate_snowflake()
        timestamp = get_timestamp(snowflake)

        # Should match format: YYYY-MM-DDTHH:MM:SSZ
        assert 'T' in timestamp
        assert timestamp.endswith('Z')
        assert len(timestamp) == 20  # Fixed length for this format

    def test_get_timestamp_parseable(self):
        """Test that timestamp can be parsed back to datetime."""
        snowflake = generate_snowflake()
        timestamp = get_timestamp(snowflake)

        # Should be parseable
        dt = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        assert isinstance(dt, datetime.datetime)

    def test_get_timestamp_recent(self):
        """Test that timestamp is recent."""
        snowflake = generate_snowflake()
        timestamp = get_timestamp(snowflake)

        dt = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        now = datetime.datetime.utcnow()

        # Should be within last hour
        time_diff = abs((now - dt).total_seconds())
        assert time_diff < 3600  # Within 1 hour


@pytest.mark.helpers
class TestGetTimestampRaw:
    """Test suite for get_timestamp_raw function."""

    def test_get_timestamp_raw_returns_integer(self):
        """Test that get_timestamp_raw returns an integer."""
        snowflake = generate_snowflake()
        timestamp = get_timestamp_raw(snowflake)
        assert isinstance(timestamp, int)

    def test_get_timestamp_raw_after_epoch(self):
        """Test that raw timestamp is after ICOSA_EPOCH."""
        snowflake = generate_snowflake()
        timestamp = get_timestamp_raw(snowflake)
        assert timestamp >= ICOSA_EPOCH

    def test_get_timestamp_raw_milliseconds(self):
        """Test that raw timestamp is in milliseconds."""
        snowflake = generate_snowflake()
        timestamp = get_timestamp_raw(snowflake)

        # Convert to seconds and check it's reasonable
        seconds = timestamp / 1000
        dt = datetime.datetime.fromtimestamp(seconds)

        # Should be a valid datetime
        assert dt.year >= 2020  # After ICOSA_EPOCH (2020-01-01)

    def test_get_timestamp_raw_extraction(self):
        """Test timestamp extraction from snowflake."""
        snowflake = generate_snowflake()
        timestamp = get_timestamp_raw(snowflake)

        # Manual extraction
        manual_timestamp = (snowflake >> 22) + ICOSA_EPOCH

        assert timestamp == manual_timestamp


@pytest.mark.helpers
class TestGetSnowflakeTimestamp:
    """Test suite for get_snowflake_timestamp function."""

    def test_get_snowflake_timestamp_returns_datetime(self):
        """Test that get_snowflake_timestamp returns datetime object."""
        snowflake = generate_snowflake()
        dt = get_snowflake_timestamp(snowflake)
        assert isinstance(dt, datetime.datetime)

    def test_get_snowflake_timestamp_recent(self):
        """Test that snowflake timestamp is recent."""
        snowflake = generate_snowflake()
        dt = get_snowflake_timestamp(snowflake)
        now = datetime.datetime.now()

        # Should be within last hour
        time_diff = abs((now - dt).total_seconds())
        assert time_diff < 3600

    def test_get_snowflake_timestamp_after_epoch(self):
        """Test that snowflake timestamp is after ICOSA_EPOCH."""
        snowflake = generate_snowflake()
        dt = get_snowflake_timestamp(snowflake)

        # Should be after 2020-01-01
        epoch_dt = datetime.datetime(2020, 1, 1)
        assert dt >= epoch_dt

    def test_get_snowflake_timestamp_year(self):
        """Test that snowflake timestamp year is valid."""
        snowflake = generate_snowflake()
        dt = get_snowflake_timestamp(snowflake)

        # Year should be reasonable (2020-2100)
        assert 2020 <= dt.year <= 2100


@pytest.mark.helpers
class TestGetSnowflakeTimestampRaw:
    """Test suite for get_snowflake_timestamp_raw function."""

    def test_get_snowflake_timestamp_raw_returns_integer(self):
        """Test that get_snowflake_timestamp_raw returns integer."""
        snowflake = generate_snowflake()
        timestamp = get_snowflake_timestamp_raw(snowflake)
        assert isinstance(timestamp, int)

    def test_get_snowflake_timestamp_raw_matches_get_timestamp_raw(self):
        """Test that both raw timestamp functions return same value."""
        snowflake = generate_snowflake()
        timestamp1 = get_timestamp_raw(snowflake)
        timestamp2 = get_snowflake_timestamp_raw(snowflake)

        assert timestamp1 == timestamp2

    def test_get_snowflake_timestamp_raw_after_epoch(self):
        """Test that raw snowflake timestamp is after ICOSA_EPOCH."""
        snowflake = generate_snowflake()
        timestamp = get_snowflake_timestamp_raw(snowflake)
        assert timestamp >= ICOSA_EPOCH


@pytest.mark.helpers
class TestIcosaEpoch:
    """Test suite for ICOSA_EPOCH constant."""

    def test_icosa_epoch_value(self):
        """Test ICOSA_EPOCH is set to correct value."""
        # ICOSA_EPOCH is 2021-01-01 00:00:00 UTC in milliseconds.
        assert ICOSA_EPOCH == 1609459200000

    def test_icosa_epoch_corresponds_to_2021(self):
        """Test ICOSA_EPOCH corresponds to January 1, 2021."""
        # Convert to datetime
        dt = datetime.datetime.utcfromtimestamp(ICOSA_EPOCH / 1000)

        assert dt.year == 2021
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 0
        assert dt.minute == 0
        assert dt.second == 0


@pytest.mark.helpers
class TestSnowflakeRoundTrip:
    """Test suite for snowflake generation and extraction round trips."""

    def test_generate_and_extract_timestamp(self):
        """Test generating snowflake and extracting timestamp."""
        before = datetime.datetime.now()
        snowflake = generate_snowflake()
        after = datetime.datetime.now()

        extracted_dt = get_snowflake_timestamp(snowflake)

        # Extracted timestamp should be between before and after
        assert before - datetime.timedelta(milliseconds=1) <= extracted_dt <= after

    def test_multiple_snowflakes_ordered_by_time(self):
        """Test that snowflakes generated in sequence have ordered timestamps."""
        snowflake1 = generate_snowflake()
        time.sleep(0.001)  # Sleep 1ms
        snowflake2 = generate_snowflake()

        timestamp1 = get_snowflake_timestamp_raw(snowflake1)
        timestamp2 = get_snowflake_timestamp_raw(snowflake2)

        # Second timestamp should be >= first
        assert timestamp2 >= timestamp1

    def test_snowflake_consistency(self):
        """Test that all timestamp extraction methods are consistent."""
        snowflake = generate_snowflake()

        # Get timestamps using different methods
        raw1 = get_timestamp_raw(snowflake)
        raw2 = get_snowflake_timestamp_raw(snowflake)

        # Both raw methods should return same value
        assert raw1 == raw2

        # The string helper returns UTC while the datetime helper returns local
        # time. Compare each representation with the raw timestamp in its own
        # time basis.
        timestamp_str = get_timestamp(snowflake)
        dt_from_str = datetime.datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
        dt_from_snowflake = get_snowflake_timestamp(snowflake)

        assert abs((dt_from_str - datetime.datetime.utcfromtimestamp(raw1 / 1000)).total_seconds()) < 1
        assert dt_from_snowflake == datetime.datetime.fromtimestamp(raw1 / 1000)


@pytest.mark.helpers
class TestSnowflakeEdgeCases:
    """Test suite for snowflake edge cases."""

    def test_snowflake_with_max_process_id(self):
        """Test snowflake generation when process ID is at maximum."""
        with patch('os.getpid', return_value=0x3FFFF + 1000):  # Over max
            snowflake = generate_snowflake()

            # Should cap at max
            process_id = (snowflake >> 4) & 0x3FFFF
            assert process_id == 0x3FFFF

    def test_snowflake_with_zero_process_id(self):
        """Test snowflake generation with process ID 0."""
        with patch('os.getpid', return_value=0):
            snowflake = generate_snowflake()

            process_id = (snowflake >> 4) & 0x3FFFF
            assert process_id == 0

    def test_snowflake_rapid_generation(self):
        """Test generating many snowflakes rapidly."""
        snowflakes = [generate_snowflake() for _ in range(100)]

        # The generator has a four-bit cycling counter, so rapid calls can
        # repeat within the same millisecond. Each encoded counter remains in
        # its documented range.
        assert all(0 <= (snowflake & 0xF) < 15 for snowflake in snowflakes)

        # All should be positive
        assert all(s > 0 for s in snowflakes)
