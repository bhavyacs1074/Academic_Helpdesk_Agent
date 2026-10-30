import asyncio
import hmac
import json
import logging
import os
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from starlette.responses import StreamingResponse

from agents.academic_agent import run_agent, stream_agent
from agents.retrieval import clear_retriever_cache
from agents.review_tickets import (
    claim_ticket,
    close_ticket,
    get_ticket,
    list_ticket_events,
    list_tickets,
    publish_ticket,
    resolve_ticket,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "")
DEFAULT_ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]
app = FastAPI(title="Academic Helpdesk Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


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


class ResolveTicketRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)

    @field_validator("answer")
    @classmethod
    def answer_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("answer must not be blank")
        return value


def _require_admin(authorization: str | None) -> None:
    if not ADMIN_API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Admin API is disabled. Configure ADMIN_API_TOKEN.",
        )
    expected = f"Bearer {ADMIN_API_TOKEN}"
    if authorization is None or not hmac.compare_digest(
        authorization.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")


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


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    session_id = request.session_id or str(uuid4())

    async def events():
        yield _sse_event("status", {"message": "Starting your request..."})
        try:
            async for event in stream_agent(
                message=request.message,
                user_id=request.user_id,
                session_id=session_id,
            ):
                yield _sse_event(event["type"], event)
        except Exception:
            logger.exception("Streaming agent request failed")
            yield _sse_event(
                "error",
                {"message": "The assistant could not complete this request."},
            )
        else:
            yield _sse_event("done", {"session_id": session_id})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/admin/tickets")
async def admin_tickets(
    status: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> list[dict]:
    _require_admin(authorization)
    allowed_statuses = {"open", "claimed", "answered", "closed"}
    if status is not None and status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Invalid ticket status.")
    return await asyncio.to_thread(list_tickets, status)


@app.post("/admin/tickets/{ticket_id}/claim")
async def admin_claim_ticket(
    ticket_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    _require_admin(authorization)
    ticket = await asyncio.to_thread(claim_ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=409, detail="Ticket is unavailable to claim.")
    return ticket


@app.post("/admin/tickets/{ticket_id}/close")
async def admin_close_ticket(
    ticket_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    _require_admin(authorization)
    ticket = await asyncio.to_thread(close_ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=409, detail="Ticket is unavailable to close.")
    return ticket


@app.post("/admin/tickets/{ticket_id}/resolve")
async def admin_resolve_ticket(
    ticket_id: str,
    request: ResolveTicketRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    _require_admin(authorization)
    ticket = await asyncio.to_thread(
        resolve_ticket,
        ticket_id,
        request.answer,
    )
    if ticket is None:
        raise HTTPException(status_code=409, detail="Ticket is unavailable to resolve.")
    return ticket


@app.post("/admin/retriever/refresh")
async def admin_refresh_retriever(
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _require_admin(authorization)
    clear_retriever_cache()
    return {"status": "retriever cache cleared"}


@app.post("/admin/tickets/{ticket_id}/publish")
async def admin_publish_ticket(
    ticket_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    _require_admin(authorization)
    try:
        ticket = await asyncio.to_thread(publish_ticket, ticket_id)
    except OSError as exc:
        logger.exception("Could not publish reviewed FAQ entry")
        raise HTTPException(
            status_code=500,
            detail="The answer is saved, but FAQ publication failed.",
        ) from exc
    if ticket is None:
        raise HTTPException(
            status_code=409,
            detail="Only an answered ticket can be published.",
        )
    clear_retriever_cache()
    return ticket


@app.get("/tickets/{ticket_id}")
async def student_ticket_status(ticket_id: str) -> dict:
    ticket = await asyncio.to_thread(get_ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Review ticket not found.")
    return {
        "ticket_id": ticket["ticket_id"],
        "status": ticket["status"],
        "resolution": ticket["resolution"],
        "created_at": ticket["created_at"],
        "updated_at": ticket["updated_at"],
    }


@app.websocket("/admin/ws")
async def admin_notifications(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin not in ALLOWED_ORIGINS or not ADMIN_API_TOKEN:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        authentication = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        token = authentication.get("token") if isinstance(authentication, dict) else None
        if not isinstance(token, str) or not hmac.compare_digest(
            token.encode("utf-8"), ADMIN_API_TOKEN.encode("utf-8")
        ):
            await websocket.close(code=1008)
            return
        after_sequence = authentication.get("after_sequence", 0)
        if not isinstance(after_sequence, int) or after_sequence < 0:
            await websocket.close(code=1008)
            return
        while True:
            events = await asyncio.to_thread(list_ticket_events, after_sequence)
            for event in events:
                await websocket.send_json(
                    {
                        "type": event["event_type"],
                        "ticket_id": event["ticket_id"],
                        "question": event["question"],
                        "status": event["status"],
                        "created_at": event["created_at"],
                        "sequence": event["sequence"],
                    }
                )
                after_sequence = event["sequence"]
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        logger.info("Admin notification WebSocket disconnected")
    except asyncio.TimeoutError:
        await websocket.close(code=1008)


def _sse_event(event_name: str, payload: dict[str, str]) -> str:
    """Encode a JSON payload as a Server-Sent Event."""
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
