from fastapi import Request, Response
from fastapi.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
import logging
from typing import Callable

from ..core.exceptions import (
    ValidationError,
    DatabaseError,
    NotFoundError,
    AuthenticationError,
    AuthorizationError,
    RateLimitError,
    FileUploadError
)

logger = logging.getLogger("wfh_monitoring.middleware")

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
            
        except ValidationError as e:
            logger.warning(f"Validation error: {str(e)}")
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
            
        except AuthenticationError as e:
            logger.warning(f"Authentication error: {str(e)}")
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
            
        except AuthorizationError as e:
            logger.warning(f"Authorization error: {str(e)}")
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
            
        except NotFoundError as e:
            logger.warning(f"Not found error: {str(e)}")
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
            
        except RateLimitError as e:
            logger.warning(f"Rate limit error: {str(e)}")
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
            
        except FileUploadError as e:
            logger.error(f"File upload error: {str(e)}")
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
            
        except DatabaseError as e:
            logger.error(f"Database error: {str(e)}")
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
            
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            ) 