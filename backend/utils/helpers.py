"""
Helper functions for the application.
Contains utility functions used across the application.
"""
import json
import time
import logging
import threading
import gzip
import io
from datetime import datetime, timezone
from functools import wraps
from bson import ObjectId, json_util
from flask import request, Response

logger = logging.getLogger(__name__)

# Request counter for monitoring
request_counter = 0
request_lock = threading.Lock()

# Cache for frequently accessed data
cache = {
    "users": {},
    "sessions": {},
    "summaries": {},
    "last_updated": {}
}

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

def ensure_timezone_aware(dt):
    """Ensure a datetime object is timezone-aware by adding UTC timezone if needed"""
    if dt and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def get_cached_data(cache_key, collection_key, query_func, ttl=60):
    """Get data from cache or execute query function if cache is stale"""
    current_time = time.time()
    
    # Check if data is in cache and not expired
    if (cache_key in cache[collection_key] and 
        cache_key in cache["last_updated"] and 
        current_time - cache["last_updated"][cache_key] < ttl):
        logger.debug(f"🔍 Cache hit for {collection_key}:{cache_key}")
        return cache[collection_key][cache_key]
    
    # Execute query function to get fresh data
    logger.debug(f"🔍 Cache miss for {collection_key}:{cache_key}")
    data = query_func()
    
    # Update cache
    cache[collection_key][cache_key] = data
    cache["last_updated"][cache_key] = current_time
    
    return data

# Performance monitoring decorator
def monitor_performance(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        global request_counter
        start_time = time.time()
        
        with request_lock:
            request_counter += 1
            current_count = request_counter
        
        result = f(*args, **kwargs)
        
        execution_time = time.time() - start_time
        logger.info(f"⏱️ {f.__name__} executed in {execution_time:.4f}s (request #{current_count})")
        
        return result
    return decorated_function

# Compression middleware
def gzip_response(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = f(*args, **kwargs)
        
        # Check if client accepts gzip encoding
        if 'gzip' in request.headers.get('Accept-Encoding', '').lower():
            content = response.data
            
            gzip_buffer = io.BytesIO()
            with gzip.GzipFile(mode='wb', fileobj=gzip_buffer) as gzip_file:
                gzip_file.write(content)
            
            response.data = gzip_buffer.getvalue()
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Content-Length'] = len(response.data)
            
        return response
    return decorated_function