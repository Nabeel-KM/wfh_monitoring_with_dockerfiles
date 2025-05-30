from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging
from bson import ObjectId
import json
from bson import json_util

logger = logging.getLogger(__name__)

def ensure_timezone_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime object is timezone-aware by adding UTC timezone if needed."""
    if dt and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def normalize_app_names(app_usage: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize application names to reduce database size."""
    normalized = {}
    for app_name, duration in app_usage.items():
        # Convert to lowercase and remove common prefixes/suffixes
        normalized_name = app_name.lower()
        normalized_name = normalized_name.replace("microsoft ", "")
        normalized_name = normalized_name.replace("google ", "")
        normalized_name = normalized_name.replace("mozilla ", "")
        normalized_name = normalized_name.replace("mozilla/", "")
        normalized_name = normalized_name.replace("chrome", "browser")
        normalized_name = normalized_name.replace("firefox", "browser")
        normalized_name = normalized_name.replace("safari", "browser")
        normalized_name = normalized_name.replace("edge", "browser")
        
        # Add duration to normalized name
        if normalized_name in normalized:
            normalized[normalized_name] += duration
        else:
            normalized[normalized_name] = duration
    
    return normalized

def calculate_session_duration(start_time: Optional[datetime], end_time: Optional[datetime]) -> int:
    """Calculate session duration in seconds."""
    if not start_time or not end_time:
        return 0
    
    start = ensure_timezone_aware(start_time)
    end = ensure_timezone_aware(end_time)
    
    if end > start:
        return int((end - start).total_seconds())
    return 0

def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def safe_get(obj: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely get nested dictionary values."""
    try:
        for key in keys:
            obj = obj[key]
        return obj
    except (KeyError, TypeError):
        return default

def log_error(endpoint: str, error: Exception) -> None:
    """Log error with endpoint context."""
    logger.error(f"Error in {endpoint}: {str(error)}", exc_info=True)

def log_request(request_id: str, method: str, path: str, status_code: int, duration: float) -> None:
    """Log request details."""
    logger.info(
        f"Request {request_id}: {method} {path} - {status_code} ({duration:.3f}s)"
    )

def serialize_mongodb_doc(doc, max_depth=10):
    """Helper function to serialize MongoDB documents"""
    try:
        # First try to use pymongo's json_util
        return json.loads(json_util.dumps(doc))
    except Exception:
        # Fall back to manual serialization if json_util fails
        def serialize(item, depth):
            if depth > max_depth:
                return str(item)
            if isinstance(item, ObjectId):
                return str(item)
            elif isinstance(item, datetime):
                return item.isoformat()
            elif isinstance(item, dict):
                return {k: serialize(v, depth + 1) for k, v in item.items()}
            elif isinstance(item, list):
                return [serialize(i, depth + 1) for i in item]
            return item
        return serialize(doc, 0) 