import asyncio
import tempfile
import unittest
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agents import retrieval, review_tickets


class FakeSessionService:
    async def get_session(self, **_: object) -> object:
        return object()


class FakeRunner:
    app_name = "test-app"
    session_service = FakeSessionService()

    def __init__(self, events: list[SimpleNamespace]) -> None:
        self.events = events

    def run_async(self, **_: object) -> AsyncIterator[SimpleNamespace]:
        async def generate_events():
            for event in self.events:
                yield event

        return generate_events()


class EmptyCollection:
    def count(self) -> int:
        return 0

    def get(self, **_: object) -> dict[str, list]:
        return {"ids": [], "documents": [], "metadatas": []}


class RetrievalEscalationTests(unittest.TestCase):
    def test_all_relevant_agents_can_create_review_tickets(self) -> None:
        from agents.academic_agent import root_agent
        from agents.email_agent import email_agent
        from agents.policy_agent import policy_agent
        from agents.schedule_agent import schedule_agent

        for agent in (root_agent, schedule_agent, policy_agent, email_agent):
            tool_names = {tool.__name__ for tool in agent.tools}
            self.assertIn("request_human_review", tool_names, agent.name)

        schedule_tool_names = {tool.__name__ for tool in schedule_agent.tools}
        self.assertIn("lookup_course", schedule_tool_names)
        self.assertIn("count_courses", schedule_tool_names)
        self.assertIn(
            "topically related or partial passages are not enough",
            root_agent.instruction,
        )
        self.assertIn(
            "If evidence is partial", schedule_agent.instruction
        )
        self.assertIn(
            "evidence is relevant but incomplete", policy_agent.instruction
        )

    def test_empty_index_creates_review_ticket_without_embedding_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "review_tickets.db"
            with (
                patch.object(review_tickets, "TICKET_DB_PATH", database),
                patch.object(retrieval, "get_collection", return_value=EmptyCollection()),
                patch.object(retrieval, "embed_texts") as embed_texts,
            ):
                retriever = retrieval.AcademicRetriever()
                result = retriever.search("Who teaches an unsupported course?")
                tickets = review_tickets.list_tickets()

            self.assertFalse(result["has_evidence"])
            self.assertIn("review_ticket", result)
            self.assertEqual(len(tickets), 1)
            embed_texts.assert_not_called()

    def test_agent_can_escalate_conflicting_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "review_tickets.db"
            with patch.object(review_tickets, "TICKET_DB_PATH", database):
                result = retrieval.request_human_review(
                    "Who teaches course X?",
                    "The current timetable and course listing disagree.",
                    "data/timetable.csv row 4; data/courses.md chunk 2",
                )
                ticket = review_tickets.get_ticket(result["ticket_id"])

        self.assertEqual(result["status"], "open")
        self.assertIn("disagree", ticket["reason"])
        self.assertIn("timetable.csv", ticket["evidence"][0]["summary"])

    def test_explicit_specialist_abstention_creates_ticket_and_replaces_reply(self) -> None:
        from agents.academic_agent import _ensure_review_ticket

        question = "Which course is the most highly rated this semester?"
        model_reply = (
            "I do not have access to student rating information for courses, "
            "so I cannot tell you which course is most highly rated. My "
            "functions allow me to look up course codes and counts. I recommend "
            "you ask this question to the academic_helpdesk_agent_orchestrator."
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "review_tickets.db"
            with patch.object(review_tickets, "TICKET_DB_PATH", database):
                result = _ensure_review_ticket(
                    question,
                    model_reply,
                    "schedule_agent",
                )
                tickets = review_tickets.list_tickets()

        self.assertIn("forwarded your question", result)
        self.assertIn("Review ticket ID:", result)
        self.assertNotIn("ask this question to", result)
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]["question"], question)
        self.assertIn(
            "Unverified specialist response:",
            tickets[0]["evidence"][0]["summary"],
        )

    def test_supported_specialist_response_does_not_create_ticket(self) -> None:
        from agents.academic_agent import _ensure_review_ticket

        response = "The course is listed in the official timetable for semester 2."
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "review_tickets.db"
            with patch.object(review_tickets, "TICKET_DB_PATH", database):
                result = _ensure_review_ticket(
                    "When is the course offered?",
                    response,
                    "schedule_agent",
                )
                tickets = review_tickets.list_tickets()

        self.assertEqual(result, response)
        self.assertEqual(tickets, [])

    def test_only_academic_specialist_abstentions_trigger_fallback(self) -> None:
        from agents.academic_agent import _ensure_review_ticket

        reply = "I cannot answer because that data is not available."
        self.assertEqual(
            _ensure_review_ticket("question", reply, "email_agent"),
            reply,
        )

    def test_streaming_withholds_specialist_abstention_until_ticket_is_created(self) -> None:
        from agents import academic_agent

        question = "Which course is the most highly rated this semester?"
        partial = "I do not have access to student rating information."
        complete = (
            "I do not have access to student rating information for courses, "
            "so I cannot tell you the highest-rated course."
        )

        def make_event(text: str, partial_event: bool) -> SimpleNamespace:
            return SimpleNamespace(
                author="schedule_agent",
                partial=partial_event,
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text=text, function_call=None),
                    ],
                ),
                get_function_calls=lambda: [],
            )

        runner = FakeRunner(
            [make_event(partial, True), make_event(complete, False)]
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "review_tickets.db"
            with (
                patch.object(academic_agent, "runner", runner),
                patch.object(review_tickets, "TICKET_DB_PATH", database),
            ):
                async def collect_stream() -> list[dict[str, str]]:
                    return [
                        event
                        async for event in academic_agent.stream_agent(
                            question,
                            "student",
                            "session",
                        )
                    ]

                events = asyncio.run(collect_stream())
                tickets = review_tickets.list_tickets()

        deltas = [event["text"] for event in events if event["type"] == "delta"]
        self.assertEqual(len(deltas), 1)
        self.assertIn("forwarded your question", deltas[0])
        self.assertNotIn(partial, deltas[0])
        self.assertEqual(len(tickets), 1)


if __name__ == "__main__":
    unittest.main()
