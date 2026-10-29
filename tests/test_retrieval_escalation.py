import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents import retrieval, review_tickets


class EmptyCollection:
    def count(self) -> int:
        return 0

    def get(self, **_: object) -> dict[str, list]:
        return {"ids": [], "documents": [], "metadatas": []}


class RetrievalEscalationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
