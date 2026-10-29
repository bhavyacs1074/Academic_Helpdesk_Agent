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
<<<<<<< HEAD
=======
from agents.retrieval import request_human_review, retrieve_academic_evidence
>>>>>>> 0ff2a07 (feat: Added the admin handover)

root_agent = Agent(
    model=create_ollama_model(),
    name="academic_helpdesk_agent_orchestrator",
    description=(
        "Dispatches academic helpdesk requests to the policy, schedule, or email "
        "specialist and returns their evidence-based response."
    ),
    instruction=(
<<<<<<< HEAD
        "You are a dispatcher, not a subject-matter answerer. For every "
        "in-scope academic request, transfer the user's full request to the "
        "appropriate specialist and do not answer it yourself. Route questions "
        "that ask to draft, edit, or reply to an academic email to email_agent, "
        "even when the request includes a course code or policy detail. Otherwise, "
        "route questions about course names or codes, course content, instructors, "
        "slots, timetables, course offerings, or course counts to schedule_agent. "
        "Route academic rules, regulations, attendance, exams, curriculum, and "
        "degree requirements to policy_agent. If a request needs more than "
        "one specialty, consult each relevant specialist before replying. Do "
        "not use your own general knowledge or make institution-specific claims. "
        "For questions outside the academic helpdesk scope, say that you do not "
        "have verified information to answer. When a specialist cannot verify "
        "an answer from its tools or documents, preserve that uncertainty in "
        "your final response instead of filling gaps."
    ),
    sub_agents=[policy_agent, schedule_agent, email_agent],
=======
        "You are the academic helpdesk orchestrator. Route questions about "
        "course names or codes, instructors, curriculum, schedules, and "
        "timetables directly to schedule_agent. This includes questions such as "
        "'Who teaches Autonomous Systems?'; do not answer these from memory, "
        "and do not ask which institution before checking the academic "
        "documents available to schedule_agent. Tell schedule_agent to use "
        "retrieved evidence and cite its source. Route academic policies, "
        "procedures, or regulations to policy_agent, and requests to draft, "
        "edit, or reply to academic emails to email_agent. For requests that "
        "need more than one specialty, consult each relevant agent. Answer "
        "other in-scope academic questions yourself. Do not invent "
        "institution-specific facts; if the relevant documents do not establish "
        "an answer, say that it could not be verified and ask only for details "
        "that would distinguish among supported courses or programs. If a "
        "retrieval result contains review_ticket.ticket_id, explain that the "
        "question was referred for human review, include the exact ID using "
        "`Review ticket ID: <id>`, and do not guess. If reliable sources "
        "conflict, call request_human_review with the original question, "
        "concise reason, and source citations in evidence_summary. Reuse an ID "
        "already returned by retrieval. Before answering, verify that the "
        "retrieved passages directly establish every requested fact and the "
        "requested answer type, such as a total, count, date, or instructor. "
        "Topically related passages are not sufficient evidence. If the "
        "passages are partial, omit the requested fact, or only describe the "
        "topic without answering it, call request_human_review with the "
        "student's original question, a concise reason, and relevant source "
        "citations in evidence_summary. Do not just say more information is "
        "needed, offer to search again, or ask the student to rephrase when "
        "the missing information is in institutional records. Then tell the "
        "student it was referred and include `Review ticket ID: <id>`. "
        "Clarify only when the question genuinely has multiple supported "
        "interpretations that the student can distinguish. Refuse only "
        "requests unrelated to academic helpdesk assistance."
    ),
    sub_agents=[policy_agent, schedule_agent, email_agent],
    tools=[retrieve_academic_evidence, request_human_review]
>>>>>>> 0ff2a07 (feat: Added the admin handover)
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
