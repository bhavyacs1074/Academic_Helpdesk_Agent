from google.adk.agents import Agent

from agents.model_config import create_ollama_model

policy_agent = Agent(
    model=create_ollama_model(),
    name="policy_agent",
    description="A specialized agent that provides information and guidance on academic policies, procedures, and regulations.",
)
