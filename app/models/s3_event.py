"""S3 Event model"""

from typing import List

from pydantic import BaseModel


class EventMetadata(BaseModel):
    event_id: str
    event_type: str
    created_at: str
    tracing_context: dict
    cloud_id: str
    folder_id: str


class Details(BaseModel):
    bucket_id: str
    object_id: str


class Message(BaseModel):
    event_metadata: EventMetadata
    details: Details


class StorageEventPayload(BaseModel):
    messages: List[Message]
