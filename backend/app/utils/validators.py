from datetime import datetime
from typing import Optional, Dict, Any
import re
from app.core.exceptions import ValidationError

def validate_username(username: str) -> None:
    """Validate username format."""
    if not username:
        raise ValidationError("Username cannot be empty")
    
    if len(username) < 3:
        raise ValidationError("Username must be at least 3 characters long")
    
    if len(username) > 50:
        raise ValidationError("Username must not exceed 50 characters")
    
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        raise ValidationError("Username can only contain letters, numbers, underscores, and hyphens")

def validate_display_name(display_name: str) -> None:
    """Validate display name format."""
    if not display_name:
        raise ValidationError("Display name cannot be empty")
    
    if len(display_name) < 2:
        raise ValidationError("Display name must be at least 2 characters long")
    
    if len(display_name) > 100:
        raise ValidationError("Display name must not exceed 100 characters")

def validate_session_data(data: Dict[str, Any]) -> None:
    """Validate session data format."""
    required_fields = ["user_id", "channel", "start_time"]
    for field in required_fields:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")
    
    if not isinstance(data["user_id"], str):
        raise ValidationError("user_id must be a string")
    
    if not isinstance(data["channel"], str):
        raise ValidationError("channel must be a string")
    
    if not isinstance(data["start_time"], datetime):
        raise ValidationError("start_time must be a datetime object")
    
    if "stop_time" in data and not isinstance(data["stop_time"], datetime):
        raise ValidationError("stop_time must be a datetime object")
    
    if "screen_shared" in data and not isinstance(data["screen_shared"], bool):
        raise ValidationError("screen_shared must be a boolean")

def validate_activity_data(data: Dict[str, Any]) -> None:
    """Validate activity data format."""
    required_fields = ["user_id", "session_id", "active_app", "timestamp"]
    for field in required_fields:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")
    
    if not isinstance(data["user_id"], str):
        raise ValidationError("user_id must be a string")
    
    if not isinstance(data["session_id"], str):
        raise ValidationError("session_id must be a string")
    
    if not isinstance(data["active_app"], str):
        raise ValidationError("active_app must be a string")
    
    if not isinstance(data["timestamp"], datetime):
        raise ValidationError("timestamp must be a datetime object")

def validate_date_range(start_date: Optional[datetime], end_date: Optional[datetime]) -> None:
    """Validate date range for queries."""
    if start_date and end_date and end_date < start_date:
        raise ValidationError("End date must be after start date")
    
    if start_date and not isinstance(start_date, datetime):
        raise ValidationError("Start date must be a datetime object")
    
    if end_date and not isinstance(end_date, datetime):
        raise ValidationError("End date must be a datetime object")

def validate_pagination_params(page: int, page_size: int) -> None:
    """Validate pagination parameters."""
    if page < 1:
        raise ValidationError("Page number must be greater than 0")
    
    if page_size < 1:
        raise ValidationError("Page size must be greater than 0")
    
    if page_size > 100:
        raise ValidationError("Page size must not exceed 100") 