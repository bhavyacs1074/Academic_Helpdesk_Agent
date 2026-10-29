import re
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
from agents.retrieval import request_human_review

root_agent = Agent(
    model=create_ollama_model(),
    name="academic_helpdesk_agent_orchestrator",
    description=(
        "Dispatches academic helpdesk requests to the policy, schedule, or email "
        "specialist and returns their evidence-based response."
    ),
    instruction=(
        "You are a dispatcher; do not answer academic questions yourself. "
        "For in-scope requests, call the matching specialist agent tool by its "
        "exact name: `policy_agent`, `schedule_agent`, or `email_agent`. Route "
        "academic rules, attendance, exams, curriculum, and degree requirements "
        "to policy_agent; courses, instructors, offerings, slots, schedules, "
        "and course counts to schedule_agent; academic email writing to "
        "email_agent. Preserve the user's full question during handoff. For "
        "multiple specialties, consult each relevant specialist. Do not use "
        "general knowledge. Specialists must verify that evidence directly "
        "answers the exact question; partial or merely related evidence is not "
        "enough. If evidence is missing, incomplete, conflicting, or an "
        "institutional fact remains unverified, ensure "
        "request_human_review is called with the original question, reason, "
        "and available citations. Reuse an existing ticket ID when provided. "
        "Only claim referral when a tool returned an ID, and include exactly "
        "`Review ticket ID: <id>`. For out-of-scope questions, reply only: "
        "`Question is out of scope.`"
    ),
    sub_agents=[policy_agent, schedule_agent, email_agent],
    tools=[request_human_review],
)

ROOT = Path(__file__).resolve().parents[1]
SESSION_DB_PATH = ROOT / ".local" / "agent_sessions.db"
SESSION_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

runner = Runner(
    agent=root_agent,
    app_name="academic_helpdesk_agent",
    session_service=SqliteSessionService(str(SESSION_DB_PATH)),
)

UNVERIFIED_RESPONSE_RE = re.compile(
    r"\b(?:"
    r"do not have access|don't have access|"
    r"recommend you ask|you should ask|ask this question to|"
    r"cannot (?:verify|answer|tell|find|determine)|can't (?:verify|answer|tell|find|determine)|"
    r"could not (?:verify|find|determine)|couldn't (?:verify|find|determine)|"
    r"not (?:available|provided|specified|included|in the (?:available )?records)|"
    r"no (?:relevant )?(?:information|data|record|source)|"
    r"unable to (?:verify|answer|find|determine)"
    r")\b",
    re.IGNORECASE,
)
SPECIALIST_AUTHORS = {"schedule_agent", "policy_agent"}


def _ensure_review_ticket(
    question: str,
    response: str,
    author: str,
) -> str:
    """Escalate explicit specialist abstentions when the model skipped the tool."""
    if author not in SPECIALIST_AUTHORS or not UNVERIFIED_RESPONSE_RE.search(response):
        return response
    ticket = request_human_review(
        question=question,
        reason="The specialist could not verify the requested information from available academic records.",
        evidence_summary=f"Unverified specialist response: {response[:1470]}",
    )
    return (
        "I could not verify this from the available academic records, so I "
        "have forwarded your question to an administrator for review.\n\n"
        f"Review ticket ID: {ticket['ticket_id']}"
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
    response_author = ""
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
                response_author = event.author

    if not response_text:
        raise RuntimeError("The agent completed without returning a text response.")

    return _ensure_review_ticket(message, response_text, response_author)


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
    status_by_agent = {
        "schedule_agent": "Checking course and schedule details...",
        "policy_agent": "Checking academic policies...",
        "email_agent": "Preparing email assistance...",
    }
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
                    if event.author not in SPECIALIST_AUTHORS:
                        yield {"type": "delta", "text": delta}
            continue

        for function_call in event.get_function_calls():
            if function_call.name == "retrieve_academic_evidence":
                yield {
                    "type": "status",
                    "message": "Searching academic documents...",
                }
            else:
                agent_name = (
                    (function_call.args or {}).get("agent_name")
                    if function_call.name == "transfer_to_agent"
                    else function_call.name
                )
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
                complete_text = final_text
            else:
                complete_text = previous_text or final_text
            if event.author in SPECIALIST_AUTHORS:
                complete_text = _ensure_review_ticket(
                    message,
                    complete_text,
                    event.author,
                )
                if complete_text:
                    yield {"type": "delta", "text": complete_text}
            elif final_text.startswith(previous_text):
                final_text = final_text[len(previous_text) :]
                if final_text:
                    yield {"type": "delta", "text": final_text}
            elif not previous_text and final_text:
                yield {"type": "delta", "text": final_text}
