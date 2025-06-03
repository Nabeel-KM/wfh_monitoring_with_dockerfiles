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
    allow_origins=["https://wfh.kryptomind.net"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
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
    
    # Log detailed request information
    logger.info(f"""
🔍 Request Details:
    Method: {request.method}
    URL: {request.url}
    Client Host: {request.client.host if request.client else 'Unknown'}
    Headers: {dict(request.headers)}
    Query Params: {dict(request.query_params)}
    Origin: {request.headers.get('origin', 'No Origin')}
    Referer: {request.headers.get('referer', 'No Referer')}
    User-Agent: {request.headers.get('user-agent', 'No User-Agent')}
""")
    
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Log response information
    logger.info(f"""
📤 Response Details:
    Status: {response.status_code}
    Duration: {duration:.3f}s
    Headers: {dict(response.headers)}
""")
    
    return response

# Add error handling middleware
@app.middleware("http")
async def error_handling(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        log_error(request.url.path, e)
        raise

# Include routers with proper prefixes
app.include_router(health.router, prefix="/api/health", tags=["Health"])
app.include_router(session.router, prefix="/api/session", tags=["Session"])
app.include_router(activity.router, prefix="/api/activity", tags=["Activity"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(screenshots.router, prefix="/api/screenshots", tags=["Screenshots"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["Metrics"])
app.include_router(history.router, prefix="/api/history", tags=["History"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    try:
        # Connect to MongoDB
        if not await connect_to_mongodb():
            logger.error("Failed to connect to MongoDB")
            raise Exception("Database connection failed")
        
        # Set up and start the scheduler only if it's not already running
        scheduler = setup_scheduler()
        if not scheduler.running:
            scheduler.start()
            logger.info("✅ Scheduler started successfully")
            
            # Setup background tasks only if scheduler is newly started
            setup_background_tasks(scheduler)
    except Exception as e:
        logger.error(f"❌ Error starting scheduler: {e}")
    
    # Store start time for uptime calculation
    app.start_time = time.time()
    
    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    try:
        # Shutdown scheduler
        scheduler = setup_scheduler()
        if scheduler.running:
            scheduler.shutdown()
            logger.info("✅ Scheduler shut down successfully")
    except Exception as e:
        logger.error(f"❌ Error shutting down scheduler: {e}")
    
    # Close MongoDB connection
    await close_mongodb_connection()
    
    logger.info("Application shutdown complete")

@app.get("/api")
async def root():
    """Root endpoint for health check."""
    return {"status": "ok", "message": "WFH Monitoring API is running"} 