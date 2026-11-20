from typing import Any, Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        code: Optional[str] = None,
        details: Any = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details
        super().__init__(message)


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found", details: Any = None) -> None:
        super().__init__(message, status.HTTP_404_NOT_FOUND, "not_found", details)


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Unauthorized", details: Any = None) -> None:
        super().__init__(message, status.HTTP_401_UNAUTHORIZED, "unauthorized", details)


class ForbiddenError(AppException):
    def __init__(self, message: str = "Forbidden", details: Any = None) -> None:
        super().__init__(message, status.HTTP_403_FORBIDDEN, "forbidden", details)


class ValidationAppError(AppException):
    def __init__(self, message: str = "Validation error", details: Any = None) -> None:
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error", details)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "code": exc.code,
            "details": exc.details,
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail if isinstance(exc.detail, str) else "Request failed",
            "code": "http_error",
            "details": exc.detail if not isinstance(exc.detail, str) else None,
        },
    )
