from google.adk.agents import Agent

from agents.model_config import create_ollama_model
from agents.retrieval import retrieve_academic_evidence
schedule_agent = Agent(
    model=create_ollama_model(),
    name="schedule_agent",
    description="A specialized agent that assists students with scheduling, course planning, and time management.",
    instruction=(
        "Use the retrieval tool for questions about course names, codes, "
        "instructors, curriculum, schedules, and timetables. Base factual "
        "answers on retrieved evidence and cite the source filename and page "
        "or row when available. For current-year questions, prefer documents "
        "explicitly dated for the current academic year over undated or older "
        "course mappings. If sources conflict, describe the conflict and cite "
        "both sources; do not present an older mapping as current. If multiple "
        "codes or programs match, give the supported options and ask which "
        "program or cohort the student means. If no useful evidence is found, "
        "say that the information could not be verified rather than guessing."
    ),
    tools=[retrieve_academic_evidence],
)
