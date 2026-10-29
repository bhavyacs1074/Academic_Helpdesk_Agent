import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import server
from agents import review_tickets


class AdminApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        database = Path(self.temporary_directory.name) / "tickets.sqlite3"
        self.token_patch = patch.object(server, "ADMIN_API_TOKEN", "test-token")
        self.database_patch = patch.object(review_tickets, "TICKET_DB_PATH", database)
        self.root_patch = patch.object(review_tickets, "ROOT", Path(self.temporary_directory.name))
        self.token_patch.start()
        self.database_patch.start()
        self.root_patch.start()
        self.client = TestClient(server.app)

    def tearDown(self) -> None:
        self.token_patch.stop()
        self.database_patch.stop()
        self.root_patch.stop()
        self.temporary_directory.cleanup()

    def test_ticket_operations_require_admin_token(self) -> None:
        self.assertEqual(self.client.get("/admin/tickets").status_code, 401)

    def test_admin_can_list_claim_and_resolve_ticket(self) -> None:
        ticket = review_tickets.create_ticket("When does the library close?")
        headers = {"Authorization": "Bearer test-token"}

        listed = self.client.get("/admin/tickets", headers=headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["ticket_id"], ticket["ticket_id"])

        claimed = self.client.post(
            f"/admin/tickets/{ticket['ticket_id']}/claim", headers=headers
        )
        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.json()["status"], "claimed")

        resolved = self.client.post(
            f"/admin/tickets/{ticket['ticket_id']}/resolve",
            headers=headers,
            json={"answer": "It closes at 9 PM."},
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.json()["status"], "answered")
        public_status = self.client.get(f"/tickets/{ticket['ticket_id']}")
        self.assertEqual(public_status.json()["resolution"], "It closes at 9 PM.")

    def test_websocket_notifies_authenticated_admin(self) -> None:
        ticket = review_tickets.create_ticket("Where is the registrar?")
        with self.client.websocket_connect(
            "/admin/ws", headers={"origin": "http://localhost:3000"}
        ) as socket:
            socket.send_json({"token": "test-token", "after_sequence": 0})
            event = socket.receive_json()
        self.assertEqual(event["type"], "ticket_created")
        self.assertEqual(event["ticket_id"], ticket["ticket_id"])

    def test_admin_can_publish_an_answered_ticket(self) -> None:
        ticket = review_tickets.create_ticket("Where is the registrar?")
        review_tickets.resolve_ticket(ticket["ticket_id"], "In the main building.")
        headers = {"Authorization": "Bearer test-token"}

        with patch.object(server, "clear_retriever_cache") as clear_cache:
            response = self.client.post(
                f"/admin/tickets/{ticket['ticket_id']}/publish",
                headers=headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()["published_at"])
        self.assertIn("In the main building.", (Path(self.temporary_directory.name) / "data" / "FAQ.md").read_text(encoding="utf-8"))
        clear_cache.assert_called_once()


if __name__ == "__main__":
    unittest.main()
