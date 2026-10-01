"""Uniform error format: {"error": {"code", "message"}}. Messages are shown to end users."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

log = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


def _error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status)


_HTTP_CODES = {
    401: "NOT_AUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, e: AppError):
        return _error(e.status, e.code, e.message)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, e: HTTPException):
        return _error(e.status_code, _HTTP_CODES.get(e.status_code, "HTTP_ERROR"), str(e.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, e: RequestValidationError):
        fields = [
            {"field": ".".join(str(p) for p in err["loc"] if p != "body"), "message": err["msg"]}
            for err in e.errors()
        ]
        first = fields[0]
        message = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
        return _error(422, "VALIDATION_ERROR", message, fields=fields)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, e: Exception):
        log.exception("Unhandled error")
        return _error(500, "INTERNAL_ERROR", "Something went wrong. Please try again.")
