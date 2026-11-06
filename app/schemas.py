from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class SQLRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=20000)
