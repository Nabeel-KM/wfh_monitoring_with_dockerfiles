import pytest
from datetime import datetime, timezone
from fastapi import status

async def test_create_activity(test_client, sample_user):
    activity_data = {
        "username": sample_user["username"],
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "apps": {"chrome": 3600, "vscode": 1800},
        "idle_time": 300
    }
    
    response = test_client.post("/api/activity", json=activity_data)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] == True
    assert "activity_id" in response.json()

async def test_invalid_activity(test_client):
    invalid_data = {
        "username": "nonexistent_user",
        "date": "invalid-date",
        "apps": {}
    }
    
    response = test_client.post("/api/activity", json=invalid_data)
    assert response.status_code == status.HTTP_404_NOT_FOUND