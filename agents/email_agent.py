from google.adk.agents import Agent

from agents.model_config import create_ollama_model

email_agent = Agent(
    model=create_ollama_model(),
    name="email_agent",
    description="A specialized agent that helps students with email communication, including drafting, editing, and responding to emails.",
)
