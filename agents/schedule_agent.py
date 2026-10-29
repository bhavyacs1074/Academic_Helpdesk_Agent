from google.adk.agents import Agent

from agents.model_config import create_ollama_model

schedule_agent = Agent(
    model=create_ollama_model(),
    name="schedule_agent",
    description="A specialized agent that assists students with scheduling, course planning, and time management.",
)
