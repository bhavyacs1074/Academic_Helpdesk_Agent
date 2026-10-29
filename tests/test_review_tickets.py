import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents import review_tickets


class ReviewTicketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database = self.root / ".local" / "review_tickets.db"
        self.database.parent.mkdir(parents=True)
        self.database_patch = patch.object(
            review_tickets, "TICKET_DB_PATH", self.database
        )
        self.root_patch = patch.object(review_tickets, "ROOT", self.root)
        self.database_patch.start()
        self.root_patch.start()

    def tearDown(self) -> None:
        self.database_patch.stop()
        self.root_patch.stop()
        self.temporary_directory.cleanup()

    def test_create_deduplicates_open_questions_and_persists(self) -> None:
        first = review_tickets.create_ticket("Who teaches course X?")
        duplicate = review_tickets.create_ticket("  WHO teaches   course x? ")

        self.assertEqual(first["ticket_id"], duplicate["ticket_id"])
        self.assertEqual(duplicate["occurrence_count"], 2)
        self.assertEqual(len(review_tickets.list_tickets("open")), 1)
        events = review_tickets.list_ticket_events(0)
        self.assertEqual(
            [event["event_type"] for event in events],
            ["ticket_created", "ticket_updated"],
        )

    def test_claim_and_resolve_ticket(self) -> None:
        ticket = review_tickets.create_ticket("When does registration open?")
        claimed = review_tickets.claim_ticket(ticket["ticket_id"])

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["status"], "claimed")
        self.assertEqual(review_tickets.claim_ticket(ticket["ticket_id"]), None)

        answered = review_tickets.resolve_ticket(
            ticket["ticket_id"], "Registration begins on Monday."
        )
        self.assertIsNotNone(answered)
        self.assertEqual(answered["status"], "answered")
        self.assertEqual(
            review_tickets.get_ticket(ticket["ticket_id"])["resolution"],
            "Registration begins on Monday.",
        )

    def test_ticket_can_be_closed_without_an_answer(self) -> None:
        ticket = review_tickets.create_ticket("Where can I get a student ID?")
        closed = review_tickets.close_ticket(ticket["ticket_id"])

        self.assertIsNotNone(closed)
        self.assertEqual(closed["status"], "closed")
        self.assertIsNone(closed["resolution"])

    def test_faq_publication_is_explicit(self) -> None:
        ticket = review_tickets.create_ticket("Where is the registrar office?")
        review_tickets.resolve_ticket(
            ticket["ticket_id"], "The office is in the main administration building."
        )
        review_tickets.publish_ticket(ticket["ticket_id"])

        faq_text = (self.root / "data" / "FAQ.md").read_text(encoding="utf-8")
        self.assertIn(ticket["ticket_id"], faq_text)
        self.assertIn("The office is in the main administration building.", faq_text)
        self.assertIsNotNone(
            review_tickets.get_ticket(ticket["ticket_id"])["published_at"]
        )


if __name__ == "__main__":
    unittest.main()
