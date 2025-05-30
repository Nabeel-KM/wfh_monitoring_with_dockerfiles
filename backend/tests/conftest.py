import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import os
import asyncio
from typing import AsyncGenerator, Generator

from app.main import app
from app.core.config import get_settings
from app.services.mongodb import mongodb

settings = get_settings()

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_client() -> AsyncGenerator:
    # Use test database
    test_db_name = "test_wfh_monitoring"
    mongodb.client = AsyncIOMotorClient(settings.MONGO_URI)
    mongodb.db = mongodb.client[test_db_name]
    
    # Create test client
    with TestClient(app) as client:
        yield client
        
    # Cleanup test database
    await mongodb.client.drop_database(test_db_name)

@pytest.fixture
async def sample_user(test_client):
    user_data = {
        "username": "test_user",
        "display_name": "Test User"
    }
    
    result = await mongodb.db.users.insert_one(user_data)
    user_data["_id"] = result.inserted_id
    return user_data