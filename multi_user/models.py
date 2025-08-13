
# models.py
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# Utility for ObjectId validation & conversion
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
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")

# Pydantic User model for validation and response
class User(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")  # Use Google sub as the Mongo _id string
    user_id: Optional[str]
    email: Optional[EmailStr]
    token: Optional[str]
    refresh_token: Optional[str]
    token_uri: Optional[str]
    client_id: Optional[str]
    client_secret: Optional[str]
    scopes: Optional[str]  # comma-separated scopes
    last_history_id: Optional[int]

    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# MongoDB client and DB instance
client = AsyncIOMotorClient("mongodb+srv://myndydev:kDmqiJbCQTihrRFx@cluster0.pjwrm2q.mongodb.net/myndy-ai-worker")
DATABASE_NAME="myndy-ai-worker"
mail_histor="users_mail_history"
state ="oauth_states"
db = client[DATABASE_NAME]
users_collection = db[mail_histor]
state_collection = db[state]
mail_service_token_collection = db["mail_service_tokens"]
