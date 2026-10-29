from google.adk.agents import Agent

from agents.model_config import create_ollama_model
from agents.retrieval import request_human_review, retrieve_academic_evidence

policy_agent = Agent(
    model=create_ollama_model(),
    name="policy_agent",
    description="A specialized agent that provides information and guidance on academic policies, procedures, and regulations.",
    instruction=(
        "Use the retrieval tool to find relevant academic policies and regulations. "
        "Base answers on retrieved evidence, cite its source, and say when no "
        "relevant evidence is found instead of guessing. If reliable sources "
        "conflict, explain the conflict and call request_human_review with the "
        "original question, concise reason, and both source citations in "
        "evidence_summary. If the retrieval result "
        "includes a review_ticket.ticket_id, tell the student the question has "
        "been referred for human review and include the exact ID using "
        "`Review ticket ID: <id>`. If retrieval already returned a ticket ID, "
        "reuse it rather than creating a duplicate. Do not invent an answer "
        "while a ticket is pending. Before answering, verify that retrieved "
        "passages directly establish every requested fact and requested answer "
        "type. Topically related policy passages are not sufficient. If the "
        "evidence is relevant but incomplete or does not answer the exact "
        "question, call request_human_review with the original question, a "
        "concise reason, and source citations in evidence_summary. Do not "
        "merely summarize partial evidence, offer to search again, or ask the "
        "student to rephrase when the missing answer is in institutional "
        "records. Then tell the student it was referred and include "
        "`Review ticket ID: <id>`. Clarify only if multiple supported "
        "interpretations require the student's choice."
    ),
    tools=[retrieve_academic_evidence, request_human_review],
)
