from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logger import Logger, LogLevel

logger = Logger("errors")


class DomainError(Exception):
    """Base class for errors the API translates into client responses."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "domain_error"

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        # JSON-serializable extra context for the client (e.g. the id of a conflicting row); omitted when None.
        self.details = details


class UnauthorizedError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class UnprocessableError(DomainError):
    """Input that passed schema validation but was rejected by a deeper rule (e.g. the database)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"


class BadGatewayError(DomainError):
    """A dependency (e.g. the LLM provider) failed or answered with something unusable."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "bad_gateway"


class ServiceUnavailableError(DomainError):
    """A feature that needs configuration this deployment does not have (e.g. no LLM API key)."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"


def _error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    """Every error leaves the API as ``{"error": {"code", "message", "details"?}}``."""
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


async def _domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    level: LogLevel = "warning" if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR else "info"
    logger.fire(
        "domain_error", level=level, code=exc.code, status=exc.status_code, path=request.url.path,
        method=request.method, error=exc.message,
    )
    return _error_response(exc.status_code, exc.code, exc.message, exc.details)


def _summarize(error: Any) -> str:
    """One validation error as ``field: message`` (just the message when it has no location)."""
    if error["loc"]:
        return f"{error['loc'][-1]}: {error['msg']}"
    return str(error["msg"])


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = exc.errors()
    message = "; ".join(_summarize(err) for err in errors) or "Invalid request"
    logger.fire("request_validation_failed", path=request.url.path, method=request.method, error=message)
    # Only loc/msg/type: `input` and `ctx` may echo client data or hold non-JSON values.
    details = [{"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in errors]
    return _error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", message, details)


async def _http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    response = _error_response(exc.status_code, "http_error", str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.fire("unhandled_error", level="error", _exc_info=exc, path=request.url.path, method=request.method)
    return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Internal server error")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
