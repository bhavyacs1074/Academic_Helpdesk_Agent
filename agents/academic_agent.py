from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.email_agent import email_agent
from agents.model_config import create_ollama_model
from agents.policy_agent import policy_agent
from agents.schedule_agent import schedule_agent

root_agent = Agent(
    model=create_ollama_model(),
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
