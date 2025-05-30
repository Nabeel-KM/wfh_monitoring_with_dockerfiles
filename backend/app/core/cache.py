from typing import Any, Dict, Optional
import time
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class Cache:
    def __init__(self, ttl: int = 300):
        """Initialize cache with TTL in seconds."""
        self._cache: Dict[str, Dict[str, Any]] = {
            "users": {},
            "sessions": {},
            "summaries": {},
            "last_updated": {}
        }
        self.ttl = ttl

    def get(self, key: str, collection: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        try:
            if (key in self._cache[collection] and 
                key in self._cache["last_updated"] and 
                time.time() - self._cache["last_updated"][key] < self.ttl):
                logger.debug(f"Cache hit for {collection}:{key}")
                return self._cache[collection][key]
            logger.debug(f"Cache miss for {collection}:{key}")
            return None
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            return None

    def set(self, key: str, value: Any, collection: str) -> bool:
        """Set value in cache with current timestamp."""
        try:
            self._cache[collection][key] = value
            self._cache["last_updated"][key] = time.time()
            return True
        except Exception as e:
            logger.error(f"Error setting cache: {e}")
            return False

    def delete(self, key: str, collection: str) -> bool:
        """Delete value from cache."""
        try:
            if key in self._cache[collection]:
                del self._cache[collection][key]
            if key in self._cache["last_updated"]:
                del self._cache["last_updated"][key]
            return True
        except Exception as e:
            logger.error(f"Error deleting from cache: {e}")
            return False

    def clear(self, collection: Optional[str] = None) -> bool:
        """Clear cache for a specific collection or all collections."""
        try:
            if collection:
                self._cache[collection].clear()
            else:
                for coll in self._cache:
                    self._cache[coll].clear()
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False

    def clean_expired(self) -> int:
        """Remove expired items from cache."""
        try:
            current_time = time.time()
            expired_keys = []
            
            # Find expired keys
            for key, timestamp in self._cache["last_updated"].items():
                if current_time - timestamp > self.ttl:
                    expired_keys.append(key)
            
            # Remove expired keys
            for key in expired_keys:
                for collection in ["users", "sessions", "summaries"]:
                    if key in self._cache[collection]:
                        del self._cache[collection][key]
                del self._cache["last_updated"][key]
            
            return len(expired_keys)
        except Exception as e:
            logger.error(f"Error cleaning expired cache items: {e}")
            return 0

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "users_cached": len(self._cache["users"]),
            "sessions_cached": len(self._cache["sessions"]),
            "summaries_cached": len(self._cache["summaries"]),
            "total_cached_items": len(self._cache["users"]) + 
                                len(self._cache["sessions"]) + 
                                len(self._cache["summaries"])
        } 