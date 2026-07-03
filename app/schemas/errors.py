from pydantic import BaseModel


class ErrorDetail(BaseModel):
    errorCode: str
    message: str


class BadRequestResponse(BaseModel):
    detail: ErrorDetail
