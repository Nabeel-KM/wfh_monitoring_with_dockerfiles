from fastapi import HTTPException, status
from typing import Any, Dict, Optional

class BaseError(HTTPException):
    """Base error class for all custom exceptions."""
    def __init__(self, detail: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        super().__init__(status_code=status_code, detail=detail)

class ValidationError(BaseError):
    """Raised when input validation fails."""
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)

class AuthenticationError(BaseError):
    """Raised when authentication fails."""
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(detail=detail, status_code=status.HTTP_401_UNAUTHORIZED)

class AuthorizationError(BaseError):
    """Raised when user is not authorized to perform an action."""
    def __init__(self, detail: str = "Not authorized"):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)

class NotFoundError(BaseError):
    """Raised when a requested resource is not found."""
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)

class RateLimitError(BaseError):
    """Raised when rate limit is exceeded."""
    def __init__(self, detail: str = "Rate limit exceeded"):
        super().__init__(detail=detail, status_code=status.HTTP_429_TOO_MANY_REQUESTS)

class FileUploadError(BaseError):
    """Raised when file upload fails."""
    def __init__(self, detail: str = "File upload failed"):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)

class DatabaseError(BaseError):
    """Raised when database operation fails."""
    def __init__(self, detail: str = "Database operation failed"):
        super().__init__(detail=detail, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CacheError(BaseError):
    """Raised when cache operation fails."""
    def __init__(self, detail: str = "Cache operation failed"):
        super().__init__(detail=detail, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ConfigurationError(BaseError):
    """Raised when there is a configuration error."""
    def __init__(self, detail: str = "Configuration error"):
        super().__init__(detail=detail, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ServiceUnavailableError(BaseError):
    """Raised when a required service is unavailable."""
    def __init__(self, detail: str = "Service unavailable"):
        super().__init__(detail=detail, status_code=status.HTTP_503_SERVICE_UNAVAILABLE) 