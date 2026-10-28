import logging
from uuid import uuid4

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from google.genai import types
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from pydantic import BaseModel, Field, field_validator

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

policy_agent = Agent(
    model=LiteLlm(
        model="ollama_chat/gemma4:e4b",
        api_base="http://localhost:11434",
        extra_body={"think": False},
    ),
    name="policy_agent",
    description="A specialized agent that provides information and guidance on academic policies, procedures, and regulations.",
)

schedule_agent = Agent(
    model=LiteLlm(
        model="ollama_chat/gemma4:e4b",
        api_base="http://localhost:11434",
        extra_body={"think": False},

    ),
    name="schedule_agent",
    description="A specialized agent that assists students with scheduling, course planning, and time management.",
)

email_agent = Agent(
    model=LiteLlm(
        model="ollama_chat/gemma4:e4b",
        api_base="http://localhost:11434",
        extra_body={"think": False},
    ),
    name="email_agent",
    description="A specialized agent that helps students with email communication, including drafting, editing, and responding to emails.",
)
root_agent = Agent(
    model=LiteLlm(
        model="ollama_chat/gemma4:e4b",
        api_base="http://localhost:11434",
        extra_body={"think": False},
    ),
    name="academic_helpdesk_agent_orchestrator",
    description="An orchestrator agent that manages multiple specialized agents to provide academic assistance to students.",
    instruction=(
        "Help students with academic questions. Delegate to policy_agent for "
        "academic policies, procedures, or regulations; schedule_agent for "
        "course planning, schedules, or time management; and email_agent for "
        "drafting, editing, or replying to academic emails. For requests that "
        "need more than one of these specialties, consult each relevant agent. "
        "Answer general academic questions yourself. Do not invent institution-"
        "specific policies; ask the student for their institution when needed."
    ),
    sub_agents=[policy_agent, schedule_agent, email_agent],
)

runner = InMemoryRunner(root_agent)
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
        session = await runner.session_service.get_session(
            app_name=runner.app_name,
            user_id=request.user_id,
            session_id=session_id,
        )
        if session is None:
            await runner.session_service.create_session(
                app_name=runner.app_name,
                user_id=request.user_id,
                session_id=session_id,
            )

        response_text = ""
        async for event in runner.run_async(
            user_id=request.user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text=request.message)],
            ),
        ):
            if event.author != "user" and event.content and event.content.parts:
                event_text = "".join(
                    part.text for part in event.content.parts if part.text
                )
                if event_text:
                    response_text = event_text

        if not response_text:
            raise HTTPException(
                status_code=502,
                detail="The agent completed without returning a text response.",
            )

        return {
            "response": response_text,
            "user_id": request.user_id,
            "session_id": session_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Agent request failed")
        raise HTTPException(
            status_code=502,
            detail="The agent failed to process the request.",
        ) from exc

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
