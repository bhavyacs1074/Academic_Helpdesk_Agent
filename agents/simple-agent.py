import asyncio

from google.adk.agents import Agent 
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from dotenv import load_dotenv

load_dotenv()

root_agent = Agent(
    model=LiteLlm(
        model="ollama_chat/qwen3:8b",
        api_base="http://localhost:11434",
    ),
    name="academic_helpdesk_agent_orchestrator",
    description="An orchestrator agent that manages multiple specialized agents to provide academic assistance to students.",
)

# Run the agent using an in-memory runner 


async def main():
    
    runner = InMemoryRunner(root_agent)
    events = await runner.run_debug("What is the difference between supervised and unsupervised learning?")

if __name__ == "__main__":
    asyncio.run(main())
