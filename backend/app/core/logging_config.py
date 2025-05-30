import logging
import sys
from typing import Optional
from datetime import datetime
import json
from fastapi import Request, Response
import time

def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging for the application."""
    # Create formatter
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Add file handler
    file_handler = logging.FileHandler('app.log')
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)

class RequestLogger:
    """Middleware for logging HTTP requests and responses."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or get_logger(__name__)
    
    async def __call__(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        # Log request
        await self.log_request(request)
        
        # Process request
        response = await call_next(request)
        
        # Log response
        self.log_response(request, response, start_time)
        
        return response
    
    async def log_request(self, request: Request) -> None:
        """Log incoming request details."""
        try:
            body = await request.body()
            body_str = body.decode() if body else ""
        except:
            body_str = ""
            
        self.logger.info(
            f"Request: {request.method} {request.url.path} - "
            f"Headers: {dict(request.headers)} - "
            f"Body: {body_str}"
        )
    
    def log_response(self, request: Request, response: Response, start_time: float) -> None:
        """Log response details."""
        duration = time.time() - start_time
        self.logger.info(
            f"Response: {request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Duration: {duration:.3f}s"
        )

def log_error(endpoint: str, error: Exception) -> None:
    """Log error with endpoint context."""
    logger = get_logger(__name__)
    logger.error(
        f"Error in {endpoint}: {str(error)}",
        exc_info=True
    )

def log_request(request_id: str, method: str, path: str, status_code: int, duration: float) -> None:
    """Log request details."""
    logger = get_logger(__name__)
    logger.info(
        f"Request {request_id}: {method} {path} - {status_code} ({duration:.3f}s)"
    )