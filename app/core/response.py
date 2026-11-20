from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: Optional[T] = None
    meta: Optional[dict[str, Any]] = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    code: Optional[str] = None
    details: Optional[Any] = None


def success_response(
    data: Any = None,
    message: str = "OK",
    meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {"success": True, "message": message, "data": data, "meta": meta}


def error_response(
    message: str,
    code: Optional[str] = None,
    details: Any = None,
) -> dict[str, Any]:
    return {"success": False, "message": message, "code": code, "details": details}
