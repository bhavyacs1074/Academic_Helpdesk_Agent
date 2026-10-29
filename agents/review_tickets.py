"""Persistent storage for questions that need human review."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TICKET_DB_PATH = ROOT / ".local" / "review_tickets.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    TICKET_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(TICKET_DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS review_tickets (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL UNIQUE,
            question TEXT NOT NULL,
            question_hash TEXT NOT NULL,
            reason TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL CHECK (status IN ('open', 'claimed', 'answered', 'closed')),
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            assigned_admin TEXT,
            resolution TEXT,
            resolved_at TEXT,
            published_at TEXT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS review_tickets_status_sequence "
        "ON review_tickets(status, sequence DESC)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS review_ticket_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return connection


def _serialize(row: sqlite3.Row) -> dict[str, Any]:
    ticket = dict(row)
    ticket["evidence"] = json.loads(ticket.pop("evidence_json"))
    return ticket


def create_ticket(
    question: str,
    reason: str = "No relevant source evidence was found.",
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", question).strip().casefold()
    if not normalized:
        raise ValueError("A review ticket requires a non-empty question.")
    question_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    now = _now()
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            """
            SELECT * FROM review_tickets
            WHERE question_hash = ? AND status IN ('open', 'claimed')
            ORDER BY sequence DESC LIMIT 1
            """,
            (question_hash,),
        ).fetchone()
        if existing:
            event_type = "ticket_updated"
            connection.execute(
                """
                UPDATE review_tickets
                SET occurrence_count = occurrence_count + 1,
                    reason = ?, last_seen_at = ?, updated_at = ?
                WHERE ticket_id = ?
                """,
                (reason, now, now, existing["ticket_id"]),
            )
            ticket_id = existing["ticket_id"]
        else:
            event_type = "ticket_created"
            ticket_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO review_tickets (
                    ticket_id, question, question_hash, reason, evidence_json,
                    status, created_at, updated_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    ticket_id,
                    question.strip(),
                    question_hash,
                    reason,
                    json.dumps(evidence or [], ensure_ascii=False),
                    now,
                    now,
                    now,
                ),
            )
        connection.execute(
            """
            INSERT INTO review_ticket_events (ticket_id, event_type, created_at)
            VALUES (?, ?, ?)
            """,
            (ticket_id, event_type, now),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM review_tickets WHERE ticket_id = ?", (ticket_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("The review ticket was not saved.")
        return _serialize(row)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def list_tickets(status: str | None = None) -> list[dict[str, Any]]:
    connection = _connect()
    try:
        query = """
            SELECT t.*, COALESCE(MAX(e.sequence), 0) AS event_sequence
            FROM review_tickets t
            LEFT JOIN review_ticket_events e ON e.ticket_id = t.ticket_id
        """
        if status:
            rows = connection.execute(
                query
                + " WHERE t.status = ? GROUP BY t.ticket_id ORDER BY t.sequence DESC",
                (status,),
            ).fetchall()
        else:
            rows = connection.execute(
                query + " GROUP BY t.ticket_id ORDER BY t.sequence DESC"
            ).fetchall()
        return [_serialize(row) for row in rows]
    finally:
        connection.close()


def get_ticket(ticket_id: str) -> dict[str, Any] | None:
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT * FROM review_tickets WHERE ticket_id = ?", (ticket_id,)
        ).fetchone()
        return _serialize(row) if row else None
    finally:
        connection.close()


def list_ticket_events(after_sequence: int) -> list[dict[str, Any]]:
    connection = _connect()
    try:
        rows = connection.execute(
            """
            SELECT e.sequence, e.event_type, t.ticket_id, t.question, t.status,
                   e.created_at
            FROM review_ticket_events e
            JOIN review_tickets t ON t.ticket_id = e.ticket_id
            WHERE e.sequence > ? ORDER BY e.sequence
            """,
            (after_sequence,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def claim_ticket(ticket_id: str, admin: str = "admin") -> dict[str, Any] | None:
    connection = _connect()
    now = _now()
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            UPDATE review_tickets
            SET status = 'claimed', assigned_admin = ?, updated_at = ?
            WHERE ticket_id = ? AND status = 'open'
            """,
            (admin, now, ticket_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            return None
        connection.commit()
        return get_ticket(ticket_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def close_ticket(ticket_id: str, admin: str = "admin") -> dict[str, Any] | None:
    connection = _connect()
    now = _now()
    try:
        cursor = connection.execute(
            """
            UPDATE review_tickets
            SET status = 'closed', assigned_admin = ?, updated_at = ?
            WHERE ticket_id = ? AND status IN ('open', 'claimed')
            """,
            (admin, now, ticket_id),
        )
        if cursor.rowcount == 0:
            return None
        connection.commit()
        return get_ticket(ticket_id)
    finally:
        connection.close()


def resolve_ticket(
    ticket_id: str,
    resolution: str,
    admin: str = "admin",
) -> dict[str, Any] | None:
    answer = resolution.strip()
    if not answer:
        raise ValueError("The resolution must not be empty.")
    connection = _connect()
    now = _now()
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            UPDATE review_tickets
            SET status = 'answered', assigned_admin = ?, resolution = ?,
                resolved_at = ?, updated_at = ?
            WHERE ticket_id = ? AND status IN ('open', 'claimed')
            """,
            (admin, answer, now, now, ticket_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            return None
        connection.commit()
        ticket = get_ticket(ticket_id)
        if ticket is None:
            raise RuntimeError("The resolved ticket could not be loaded.")
        return ticket
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def publish_ticket(ticket_id: str) -> dict[str, Any] | None:
    ticket = get_ticket(ticket_id)
    if ticket is None or ticket["status"] != "answered" or not ticket["resolution"]:
        return None
    if ticket["published_at"]:
        return ticket
    _publish_faq_entry(ticket)
    published_at = _now()
    connection = _connect()
    try:
        connection.execute(
            "UPDATE review_tickets SET published_at = ?, updated_at = ? WHERE ticket_id = ?",
            (published_at, published_at, ticket_id),
        )
        connection.commit()
    finally:
        connection.close()
    return get_ticket(ticket_id)


def _publish_faq_entry(ticket: dict[str, Any]) -> None:
    faq_path = ROOT / "data" / "FAQ.md"
    faq_path.parent.mkdir(parents=True, exist_ok=True)
    existing = faq_path.read_text(encoding="utf-8") if faq_path.exists() else ""
    marker = f"<!-- review-ticket:{ticket['ticket_id']} -->"
    if marker in existing:
        return
    question = "\n".join(f"> {line}" for line in ticket["question"].splitlines())
    answer = "\n".join(f"> {line}" for line in ticket["resolution"].splitlines())
    entry = (
        f"\n\n{marker}\n## Reviewed answer\n\n"
        f"**Question:**\n{question}\n\n**Answer:**\n{answer}\n\n"
        f"Reviewed: {ticket['resolved_at']}\n"
    )
    with faq_path.open("a", encoding="utf-8") as faq_file:
        faq_file.write(entry)
