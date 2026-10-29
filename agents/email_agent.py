from google.adk.agents import Agent

from agents.model_config import create_ollama_model
from agents.retrieval import request_human_review, retrieve_academic_evidence
email_agent = Agent(
    model=create_ollama_model(),
    name="email_agent",
    description="A specialized agent that helps students with email communication, including drafting, editing, and responding to emails.",
    instruction=(
        "Use retrieval to find relevant academic policies when needed. If "
        "retrieved passages are relevant but do not establish the fact needed "
        "for the requested email, call request_human_review with the student's "
        "original question and a concise reason instead of inventing policy "
        "details. Include `Review ticket ID: <id>` when referring the student."
    ),
    tools=[retrieve_academic_evidence, request_human_review],
)
