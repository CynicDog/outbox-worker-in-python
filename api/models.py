from pydantic import BaseModel


class JobRequest(BaseModel):
    values: list[float]
    sleep_secs: float = 1.0


class JobResponse(BaseModel):
    id: str
    status: str
    result: list[float] | None = None
    error: str | None = None
