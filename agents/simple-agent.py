import asyncio

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from dotenv import load_dotenv

load_dotenv()
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
# Run the agent using an in-memory runner


async def main():
    
    runner = InMemoryRunner(root_agent)
    events = await runner.run_debug("Write a mail to the proffessor asking for a sick leave")

if __name__ == "__main__":
    asyncio.run(main())
