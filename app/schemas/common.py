from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class MessageOut(BaseModel):
    message: str


class IdOut(BaseModel):
    id: str


class HealthOut(BaseModel):
    status: str
    app: str
    env: str
    ai_mode: str
    payment_mode: str
    storage_mode: str
