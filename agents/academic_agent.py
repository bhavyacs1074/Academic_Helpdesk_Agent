from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.email_agent import email_agent
from agents.model_config import create_ollama_model
from agents.policy_agent import policy_agent
from agents.schedule_agent import schedule_agent
from agents.retrieval import retrieve_academic_evidence

root_agent = Agent(
    model=create_ollama_model(),
    name="academic_helpdesk_agent_orchestrator",
    description="An orchestrator agent that manages multiple specialized agents to provide academic assistance to students.",
    instruction=(
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
        "that would distinguish among supported courses or programs. Refuse "
        "only requests unrelated to academic helpdesk assistance."
        "Try to answer the query in one shot as much as possible , give detailed output"
    ),
    sub_agents=[policy_agent, schedule_agent, email_agent],
    tools=[retrieve_academic_evidence]
)

runner = InMemoryRunner(root_agent)


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
