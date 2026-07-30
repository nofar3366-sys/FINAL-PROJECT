"""Timezone helpers for consistent UTC comparisons with PostgreSQL/Supabase."""

from datetime import date, datetime, time, timezone

UTC = timezone.utc


def utc_now() -> datetime:
    """Current UTC time as an aware datetime."""

    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalize naive or aware datetimes to UTC-aware values."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def combine_utc(day: date, clock: time) -> datetime:
    """Combine a local calendar date and clock into a UTC-aware datetime."""

    naive_clock = clock.replace(tzinfo=None) if clock.tzinfo is not None else clock
    return datetime.combine(day, naive_clock, tzinfo=UTC)
