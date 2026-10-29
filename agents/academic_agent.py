from collections.abc import AsyncIterator
from pathlib import Path

from google.adk.agents import Agent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types

from agents.email_agent import email_agent
from agents.model_config import create_ollama_model
from agents.policy_agent import policy_agent
from agents.schedule_agent import schedule_agent
from agents.retrieval import request_human_review, retrieve_academic_evidence

root_agent = Agent(
    model=create_ollama_model(),
    name="academic_helpdesk_agent_orchestrator",
    description=(
        "Dispatches academic helpdesk requests to the policy, schedule, or email "
        "specialist and returns their evidence-based response."
    ),
    instruction=(
        "You are a dispatcher, not a subject-matter answerer. For every "
        "in-scope academic request, transfer the user's full request to the "
        "appropriate specialist and do not answer it yourself. Route requests "
        "to draft, edit, or reply to an academic email to email_agent, even "
        "when they include a course code or policy detail. Otherwise route "
        "course names/codes, course content, instructors, slots, timetables, "
        "offerings, and course counts to schedule_agent. Route academic rules, "
        "regulations, attendance, exams, curriculum, and degree requirements "
        "to policy_agent. For requests needing multiple specialties, consult "
        "each relevant specialist before replying. Do not use general knowledge "
        "or make institution-specific claims. Preserve uncertainty when a "
        "specialist cannot verify an answer from tools or documents. The "
        "specialist must verify that evidence directly answers the exact "
        "question; topically related or partial passages are not enough. If "
        "evidence is incomplete, sources conflict, or a requested fact such as "
        "a count is not established, the specialist must call "
        "request_human_review with the user's original question, a concise "
        "reason, and source citations/evidence summary. If a specialist returns "
        "an unverified answer without creating a ticket, call "
        "request_human_review yourself before replying. Do not accept an offer "
        "to search again, a request to rephrase, or a partial summary instead "
        "of escalation when the missing information is an institutional fact. "
        "Reuse an existing review ticket ID if retrieval already created one. "
        "When a ticket is created, tell the user it was referred and include "
        "exactly `Review ticket ID: <id>` using the tool's returned ID. Never "
        "claim referral without a returned ticket ID. Ask the user to clarify "
        "only when multiple supported interpretations genuinely require their "
        "choice. For out-of-scope requests, state that you cannot help."
    ),
    sub_agents=[policy_agent, schedule_agent, email_agent],
    tools=[retrieve_academic_evidence, request_human_review],
)

ROOT = Path(__file__).resolve().parents[1]
SESSION_DB_PATH = ROOT / ".local" / "agent_sessions.db"
SESSION_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

runner = Runner(
    agent=root_agent,
    app_name="academic_helpdesk_agent",
    session_service=SqliteSessionService(str(SESSION_DB_PATH)),
)


async def run_agent(message: str, user_id: str, session_id: str) -> str:
    session = await runner.session_service.get_session(
        app_name=runner.app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        await runner.session_service.create_session(
            app_name=runner.app_name,
            user_id=user_id,
            session_id=session_id,
        )

    response_text = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=message)],
        ),
    ):
        if event.author != "user" and event.content and event.content.parts:
            event_text = "".join(
                part.text for part in event.content.parts if part.text
            )
            if event_text:
                response_text = event_text

    if not response_text:
        raise RuntimeError("The agent completed without returning a text response.")

    return response_text


async def stream_agent(
    message: str,
    user_id: str,
    session_id: str,
) -> AsyncIterator[dict[str, str]]:
    session = await runner.session_service.get_session(
        app_name=runner.app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        await runner.session_service.create_session(
            app_name=runner.app_name,
            user_id=user_id,
            session_id=session_id,
        )

    streamed_text: dict[str, str] = {}
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=message)],
        ),
        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
    ):
        if event.partial:
            if event.content and event.content.parts:
                delta = "".join(
                    part.text or ""
                    for part in event.content.parts
                    if part.text and not part.function_call
                )
                if delta:
                    streamed_text[event.author] = (
                        streamed_text.get(event.author, "") + delta
                    )
                    yield {"type": "delta", "text": delta}
            continue

        for function_call in event.get_function_calls():
            if function_call.name == "retrieve_academic_evidence":
                yield {
                    "type": "status",
                    "message": "Searching academic documents...",
                }
            elif function_call.name == "transfer_to_agent":
                agent_name = (function_call.args or {}).get("agent_name")
                status_by_agent = {
                    "schedule_agent": "Checking course and schedule details...",
                    "policy_agent": "Checking academic policies...",
                    "email_agent": "Preparing email assistance...",
                }
                if isinstance(agent_name, str) and agent_name in status_by_agent:
                    yield {
                        "type": "status",
                        "message": status_by_agent[agent_name],
                    }

        if event.content and event.content.parts:
            final_text = "".join(
                part.text or ""
                for part in event.content.parts
                if part.text and not part.function_call
            )
            previous_text = streamed_text.pop(event.author, "")
            if final_text.startswith(previous_text):
                final_text = final_text[len(previous_text) :]
            elif previous_text:
                final_text = ""
            if final_text:
                yield {"type": "delta", "text": final_text}
