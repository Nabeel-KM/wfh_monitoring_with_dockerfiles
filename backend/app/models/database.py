from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, _schema_generator, _field_schema):
        _field_schema.update(type="string")

class User(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id")
    username: str
    display_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )

class Session(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id")
    user_id: PyObjectId
    channel: Optional[str] = None
    screen_shared: bool = False
    screen_share_time: int = 0
    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    event: str
    timestamp: datetime
    total_working_hours: int = 0
    active_app: Optional[str] = None
    active_apps: List[str] = []

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )

class Activity(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id")
    user_id: PyObjectId
    session_id: PyObjectId
    active_app: str
    active_apps: List[str]
    timestamp: datetime

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )

class DailySummary(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id")
    user_id: PyObjectId
    date: str
    total_active_time: int = 0
    total_idle_time: int = 0
    total_screen_share_time: int = 0
    app_summaries: List[Dict[str, Any]] = []
    last_updated: datetime

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    ) 