"""SQLite-based caching layer with TTL management."""

import logging
import pickle
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with value and age metadata."""

    value: Any
    age_seconds: float


@dataclass
class CacheMetrics:
    """Cache performance metrics."""

    total_entries: int
    total_hits: int
    avg_hits_per_entry: float
    hit_rate: float  # Percentage of cache hits vs total requests
    total_misses: int
    avg_age_seconds: float  # Average age of cached entries
    expired_entries: int  # Count of expired entries pending cleanup


class SQLiteCacheLayer:
    """SQLite-based caching layer with TTL and invalidation support.

    Uses SQLite for persistence, simplicity, and zero-config deployment.
    Perfect for startup-scale operations without Redis overhead.
    """

    def __init__(self, db_path: Path | str = "state/signal_cache.db"):
        """Initialize SQLite cache layer.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._total_requests = 0  # Track total cache requests for hit rate
        self._total_hits = 0  # Track cache hits
        self._init_db()
        self.vacuum()  # Optimize database on startup

    def _init_db(self):
        """Initialize SQLite database with cache table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value BLOB,
                    expires_at REAL,
                    created_at REAL,
                    hit_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)")
            conn.commit()

    async def get(self, key: str) -> CacheEntry | None:
        """Retrieve cached value if not expired.

        Args:
            key: Cache key

        Returns:
            CacheEntry with value and age, or None if not found/expired
        """
        self._total_requests += 1

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT value, expires_at, created_at FROM cache WHERE key = ? AND expires_at > ?",
                    (key, datetime.now().timestamp()),
                )
                row = cursor.fetchone()

                if row:
                    # Update hit count
                    conn.execute("UPDATE cache SET hit_count = hit_count + 1 WHERE key = ?", (key,))
                    conn.commit()

                    self._total_hits += 1
                    value = pickle.loads(row[0])
                    age = datetime.now().timestamp() - row[2]
                    return CacheEntry(value=value, age_seconds=age)

                return None
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int):
        """Store value with TTL.

        Args:
            key: Cache key
            value: Value to cache (must be picklable)
            ttl_seconds: Time-to-live in seconds
        """
        try:
            expires_at = (datetime.now() + timedelta(seconds=ttl_seconds)).timestamp()
            created_at = datetime.now().timestamp()

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, expires_at, created_at) VALUES (?, ?, ?, ?)",
                    (key, pickle.dumps(value), expires_at, created_at),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")

    async def invalidate(self, pattern: str):
        """Invalidate cache entries matching pattern (SQL LIKE syntax).

        Args:
            pattern: SQL LIKE pattern (e.g., "orderbook:%" for all orderbook entries)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM cache WHERE key LIKE ?", (pattern,))
                deleted_count = cursor.rowcount
                conn.commit()

                if deleted_count > 0:
                    logger.info(
                        f"Invalidated {deleted_count} cache entries matching pattern: {pattern}"
                    )
        except Exception as e:
            logger.error(f"Cache invalidate error for pattern {pattern}: {e}")

    async def invalidate_by_key(self, key: str):
        """Invalidate a specific cache entry by exact key match.

        Args:
            key: Exact cache key to invalidate
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                deleted = cursor.rowcount > 0
                conn.commit()

                if deleted:
                    logger.debug(f"Invalidated cache entry: {key}")
        except Exception as e:
            logger.error(f"Cache invalidate error for key {key}: {e}")

    async def invalidate_all(self):
        """Invalidate all cache entries (forced refresh scenario).

        This is useful for scenarios requiring a complete cache refresh,
        such as after configuration changes or detected data inconsistencies.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM cache")
                deleted_count = cursor.rowcount
                conn.commit()

                logger.warning(f"Invalidated all cache entries: {deleted_count} entries removed")
        except Exception as e:
            logger.error(f"Cache invalidate all error: {e}")

    async def cleanup_expired(self):
        """Remove expired entries (run periodically)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM cache WHERE expires_at < ?", (datetime.now().timestamp(),)
                )
                deleted_count = cursor.rowcount
                conn.commit()

                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} expired cache entries")
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")

    def vacuum(self):
        """Optimize database (run on startup or periodically)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("VACUUM")
                conn.commit()
                logger.info("Cache database vacuumed successfully")
        except Exception as e:
            logger.error(f"Cache vacuum error: {e}")

    def get_metrics(self) -> CacheMetrics:
        """Return cache hit rate and other metrics.

        Returns:
            CacheMetrics with performance statistics including:
            - Total valid entries
            - Total hits from database
            - Average hits per entry
            - Hit rate percentage
            - Total misses
            - Average age of entries
            - Count of expired entries
        """
        try:
            now = datetime.now().timestamp()

            with sqlite3.connect(self.db_path) as conn:
                # Get valid entries metrics
                cursor = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_entries,
                        SUM(hit_count) as total_hits,
                        AVG(hit_count) as avg_hits_per_entry,
                        AVG(? - created_at) as avg_age_seconds
                    FROM cache
                    WHERE expires_at > ?
                """,
                    (now, now),
                )
                row = cursor.fetchone()

                total_entries = row[0] or 0
                total_hits = row[1] or 0
                avg_hits_per_entry = row[2] or 0.0
                avg_age_seconds = row[3] or 0.0

                # Get expired entries count
                cursor = conn.execute("SELECT COUNT(*) FROM cache WHERE expires_at <= ?", (now,))
                expired_entries = cursor.fetchone()[0] or 0

                # Calculate hit rate from tracked requests
                total_misses = self._total_requests - self._total_hits
                hit_rate = (
                    (self._total_hits / self._total_requests * 100.0)
                    if self._total_requests > 0
                    else 0.0
                )

                return CacheMetrics(
                    total_entries=total_entries,
                    total_hits=total_hits,
                    avg_hits_per_entry=avg_hits_per_entry,
                    hit_rate=hit_rate,
                    total_misses=total_misses,
                    avg_age_seconds=avg_age_seconds,
                    expired_entries=expired_entries,
                )
        except Exception as e:
            logger.error(f"Cache metrics error: {e}")
            return CacheMetrics(
                total_entries=0,
                total_hits=0,
                avg_hits_per_entry=0.0,
                hit_rate=0.0,
                total_misses=0,
                avg_age_seconds=0.0,
                expired_entries=0,
            )

    async def start_periodic_cleanup(self, interval_seconds: int = 300):
        """Start periodic cache cleanup task.

        This method runs in the background and periodically removes expired entries.
        Should be called from an async context (e.g., signal service event loop).

        Args:
            interval_seconds: Cleanup interval in seconds (default: 5 minutes)
        """
        import asyncio

        logger.info(f"Starting periodic cache cleanup (interval: {interval_seconds}s)")

        try:
            while True:
                # Break sleep into 1-second chunks for responsive cancellation
                for _ in range(interval_seconds):
                    await asyncio.sleep(1)
                await self.cleanup_expired()
        except asyncio.CancelledError:
            logger.info("Periodic cache cleanup cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in periodic cache cleanup: {e}")

    def reset_metrics(self):
        """Reset cache hit/miss tracking metrics.

        Useful for getting fresh metrics after a specific time period.
        """
        self._total_requests = 0
        self._total_hits = 0
        logger.debug("Cache metrics reset")

    def close(self):
        """Close cache connections and cleanup.

        Note: SQLite connections are managed via context managers,
        so this is primarily for explicit cleanup signaling.
        """
        logger.debug("Cache layer closed")
