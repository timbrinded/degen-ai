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
        self._init_db()

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
                conn.execute("DELETE FROM cache WHERE key LIKE ?", (pattern,))
                conn.commit()
        except Exception as e:
            logger.error(f"Cache invalidate error for pattern {pattern}: {e}")

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
            CacheMetrics with performance statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_entries,
                        SUM(hit_count) as total_hits,
                        AVG(hit_count) as avg_hits_per_entry
                    FROM cache
                    WHERE expires_at > ?
                """,
                    (datetime.now().timestamp(),),
                )
                row = cursor.fetchone()

                return CacheMetrics(
                    total_entries=row[0] or 0,
                    total_hits=row[1] or 0,
                    avg_hits_per_entry=row[2] or 0.0,
                )
        except Exception as e:
            logger.error(f"Cache metrics error: {e}")
            return CacheMetrics(total_entries=0, total_hits=0, avg_hits_per_entry=0.0)

    def close(self):
        """Close cache connections and cleanup.

        Note: SQLite connections are managed via context managers,
        so this is primarily for explicit cleanup signaling.
        """
        logger.debug("Cache layer closed")
