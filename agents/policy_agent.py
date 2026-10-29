from google.adk.agents import Agent

from agents.model_config import create_ollama_model
from agents.retrieval import retrieve_academic_evidence

policy_agent = Agent(
    model=create_ollama_model(),
    name="policy_agent",
    description="A specialized agent that provides information and guidance on academic policies, procedures, and regulations.",
    instruction=(
        "Use the retrieval tool to find relevant academic policies and regulations. "
        "Base answers on retrieved evidence, cite its source, and say when no "
        "relevant evidence is found instead of guessing."
    ),
    tools=[retrieve_academic_evidence],
)
