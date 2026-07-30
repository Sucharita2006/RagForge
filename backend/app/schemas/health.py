from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"


class ReadyResponse(BaseModel):
    status: str
    database: bool
