from google.adk.agents import Agent

from agents.model_config import create_ollama_model
<<<<<<< HEAD
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
=======
from agents.retrieval import request_human_review, retrieve_academic_evidence
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
        "course mappings. If sources conflict, describe the conflict, cite "
        "both sources, and call request_human_review with the original "
        "question, concise reason, and both source citations in "
        "evidence_summary. Do not present an older mapping as "
        "current. If multiple "
        "codes or programs match, give the supported options and ask which "
        "program or cohort the student means. If no useful evidence is found, "
        "say that the information could not be verified rather than guessing. "
        "If the retrieval result includes a review_ticket.ticket_id, tell the "
        "student the question has been referred for human review and include "
        "the exact ID using `Review ticket ID: <id>`. If retrieval already "
        "returned a ticket ID, reuse it instead of creating a duplicate. Do "
        "not invent an answer while a ticket is pending."
    ),
    tools=[retrieve_academic_evidence, request_human_review],
>>>>>>> 0ff2a07 (feat: Added the admin handover)
)
