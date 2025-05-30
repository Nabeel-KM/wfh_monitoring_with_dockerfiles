from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from .core.scheduler import setup_scheduler
from .services.mongodb import connect_to_mongodb, close_mongodb_connection
from .routers import (
    health,
    session,
    activity,
    dashboard,
    screenshots,
    metrics,
    history,
    users
)
import logging
import time
from datetime import datetime, timezone

from .core.logging_config import setup_logging, log_request, log_error
from .core.background_tasks import setup_background_tasks

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="WFH Monitoring API",
    description="API for monitoring work-from-home activities",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://wfh.kryptomind.net"],  # Specific origin
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*", "cache-control", "content-type", "authorization"],
    expose_headers=["*"],
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Add Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(time.time()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    log_request(
        request_id=request.headers.get("X-Request-ID", str(time.time())),
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration=duration
    )
    
    return response

# Add error handling middleware
@app.middleware("http")
async def error_handling(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        log_error(request.url.path, e)
        raise

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(session.router, prefix="/api", tags=["Session"])
app.include_router(activity.router, prefix="/api", tags=["Activity"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(screenshots.router, prefix="/api", tags=["Screenshots"])
app.include_router(metrics.router, prefix="/api", tags=["Metrics"])
app.include_router(history.router, prefix="/api", tags=["History"])
app.include_router(users.router, prefix="/api", tags=["Users"])

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    try:
        # Connect to MongoDB
        if not await connect_to_mongodb():
            logger.error("Failed to connect to MongoDB")
            raise Exception("Database connection failed")
        
        # Set up and start the scheduler
        scheduler = setup_scheduler()
        scheduler.start()
        logger.info("✅ Scheduler started successfully")
    except Exception as e:
        logger.error(f"❌ Error starting scheduler: {e}")
    
    # Setup background tasks
    setup_background_tasks(scheduler)
    
    # Store start time for uptime calculation
    app.start_time = time.time()
    
    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    try:
        # Shutdown scheduler
        scheduler = setup_scheduler()
        scheduler.shutdown()
        logger.info("✅ Scheduler shut down successfully")
    except Exception as e:
        logger.error(f"❌ Error shutting down scheduler: {e}")
    
    # Close MongoDB connection
    await close_mongodb_connection()
    
    logger.info("Application shutdown complete")

@app.get("/")
async def root():
    """Root endpoint for health check."""
    return {"status": "ok", "message": "WFH Monitoring API is running"} 