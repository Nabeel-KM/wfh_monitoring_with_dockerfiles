"""
Health routes for handling health-related API endpoints.
"""
import logging
import time
from datetime import datetime, timezone
from flask import Blueprint, jsonify
from mongodb import users_collection
from services.s3_service import s3_service

logger = logging.getLogger(__name__)

# Create Blueprint
health_bp = Blueprint('health', __name__)

@health_bp.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    health_data = {
        "status": "healthy",
        "components": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Check database connection
    try:
        start_time = time.time()
        users_collection.find_one({})
        db_response_time = time.time() - start_time
        health_data["components"]["database"] = {
            "status": "connected",
            "response_time_ms": round(db_response_time * 1000, 2)
        }
    except Exception as e:
        health_data["status"] = "unhealthy"
        health_data["components"]["database"] = {
            "status": "error",
            "error": str(e)
        }
        logger.error(f"❌ Database health check failed: {e}")
    
    # Check S3 connection
    try:
        start_time = time.time()
        s3_service.s3_client.list_buckets()
        s3_response_time = time.time() - start_time
        health_data["components"]["s3"] = {
            "status": "connected",
            "response_time_ms": round(s3_response_time * 1000, 2)
        }
    except Exception as e:
        health_data["status"] = "unhealthy"
        health_data["components"]["s3"] = {
            "status": "error",
            "error": str(e)
        }
        logger.error(f"❌ S3 health check failed: {e}")
    
    # Check memory usage
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        health_data["components"]["memory"] = {
            "status": "ok" if memory_mb < 500 else "warning",
            "usage_mb": round(memory_mb, 2)
        }
    except Exception as e:
        health_data["components"]["memory"] = {
            "status": "unknown",
            "error": str(e)
        }
    
    # Check MongoDB connection pool
    try:
        from mongodb import mongo_connection
        server_status = mongo_connection.client.admin.command('serverStatus')
        conn_stats = server_status.get('connections', {})
        current = conn_stats.get('current', 0)
        available = conn_stats.get('available', 0)
        max_conns = current + available
        usage_percent = (current / max_conns * 100) if max_conns > 0 else 0
        
        health_data["components"]["db_pool"] = {
            "status": "ok" if usage_percent < 80 else "warning",
            "current": current,
            "available": available,
            "usage_percent": round(usage_percent, 1)
        }
    except Exception as e:
        health_data["components"]["db_pool"] = {
            "status": "unknown",
            "error": str(e)
        }
    
    # Return appropriate status code
    status_code = 200 if health_data["status"] == "healthy" else 500
    return jsonify(health_data), status_code