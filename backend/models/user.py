"""
User model for MongoDB.
"""
from datetime import datetime
from typing import Dict, Any, Optional

class User:
    """User model for MongoDB"""
    
    @staticmethod
    def create(username: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        """Create a new user document"""
        return {
            "username": username,
            "display_name": display_name or username,
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow(),
            "is_active": True
        }
    
    @staticmethod
    def validate(data: Dict[str, Any]) -> bool:
        """Validate user data"""
        required_fields = ["username"]
        return all(field in data for field in required_fields)