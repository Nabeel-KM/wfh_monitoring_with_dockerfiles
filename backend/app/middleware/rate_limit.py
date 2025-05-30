from fastapi import Request, Response
from fastapi.middleware.base import BaseHTTPMiddleware
import time
import logging
from typing import Callable, Dict, Tuple
from collections import defaultdict
import asyncio
from ..core.exceptions import RateLimitError

logger = logging.getLogger("wfh_monitoring.middleware")

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst_limit: int = 10
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.requests: Dict[str, list] = defaultdict(list)
        self.lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host
        current_time = time.time()

        async with self.lock:
            # Clean up old requests
            self.requests[client_ip] = [
                req_time for req_time in self.requests[client_ip]
                if current_time - req_time < 60
            ]

            # Check burst limit
            if len(self.requests[client_ip]) >= self.burst_limit:
                logger.warning(f"Burst limit exceeded for IP: {client_ip}")
                raise RateLimitError(
                    detail="Too many requests in a short time. Please try again later."
                )

            # Check rate limit
            if len(self.requests[client_ip]) >= self.requests_per_minute:
                logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                raise RateLimitError(
                    detail="Rate limit exceeded. Please try again later."
                )

            # Add current request
            self.requests[client_ip].append(current_time)

        # Process the request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(
            self.requests_per_minute - len(self.requests[client_ip])
        )
        response.headers["X-RateLimit-Reset"] = str(
            int(current_time + 60)
        )

        return response 