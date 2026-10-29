from google.adk.agents import Agent

from agents.model_config import create_ollama_model
from agents.retrieval import retrieve_academic_evidence
from tools.academic_tools import count_courses, lookup_course


schedule_agent = Agent(
    model=create_ollama_model(),
    name="schedule_agent",
    description=(
        "Handles course catalog questions, course codes and names, course slots, "
        "timetables, semester offerings, and course counts by department, level, "
        "or elective category."
    ),
    instruction=(
        "You are the course catalog and scheduling specialist. For a course "
        "lookup by name or code, call lookup_course. For a question asking how "
        "many courses match filters such as department, semester, level, or "
        "elective status, call count_courses; do not estimate or count from "
        "memory. Use retrieve_academic_evidence for descriptive course-content "
        "questions or supporting passages not represented in the structured "
        "course records. Base factual claims only on tool results and cite the "
        "returned source path and row or line. Treat missing semester/year data "
        "as unknown. If the requested semester or academic year is ambiguous, "
        "ask a short clarification. If records conflict, describe the conflict "
        "and cite both sources; do not present an older offering as current. "
        "If no useful evidence is found, say the information could not be "
        "verified rather than guessing."
    ),
    tools=[lookup_course, count_courses, retrieve_academic_evidence],
)
