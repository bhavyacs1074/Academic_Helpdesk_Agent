import logging
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from agents.academic_agent import run_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Academic Helpdesk Agent")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(default="default_user", min_length=1, max_length=128)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    session_id = request.session_id or str(uuid4())

    try:
        response = await run_agent(
            message=request.message,
            user_id=request.user_id,
            session_id=session_id,
        )
    except Exception as exc:
        logger.exception("Agent request failed")
        raise HTTPException(
            status_code=502,
            detail="The agent failed to process the request.",
        ) from exc

    return {
        "response": response,
        "user_id": request.user_id,
        "session_id": session_id,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
