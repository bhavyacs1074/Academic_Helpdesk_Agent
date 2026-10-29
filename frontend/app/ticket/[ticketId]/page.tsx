"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

type TicketStatus = {
  ticket_id: string;
  status: "open" | "claimed" | "answered" | "closed";
  resolution: string | null;
  created_at: string;
  updated_at: string;
};

const API_BASE =
  (process.env.NEXT_PUBLIC_ADMIN_API_URL || "http://127.0.0.1:8000").replace(
    /\/+$/,
    "",
  );

export default function TicketStatusPage() {
  return (
    <Suspense fallback={<main className="ticket-status-shell">Loading ticket…</main>}>
      <TicketStatusContent />
    </Suspense>
  );
}

function TicketStatusContent() {
  const { ticketId } = useParams<{ ticketId: string }>();
  const [ticket, setTicket] = useState<TicketStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    async function checkStatus() {
      try {
        const response = await fetch(`${API_BASE}/tickets/${ticketId}`);
        if (!response.ok) {
          throw new Error(
            response.status === 404
              ? "This review ticket was not found."
              : `Could not check the ticket (${response.status}).`,
          );
        }
        const result = (await response.json()) as TicketStatus;
        if (!active) return;
        setTicket(result);
        setError("");
        if (result.status === "open" || result.status === "claimed") {
          timer = setTimeout(() => void checkStatus(), 4000);
        }
      } catch (requestError) {
        if (!active) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not check the ticket.",
        );
        timer = setTimeout(() => void checkStatus(), 5000);
      }
    }

    void checkStatus();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [ticketId]);

  return (
    <main className="ticket-status-shell">
      <section className="ticket-status-card">
        <Link className="ticket-status-back" href="/">Academic Helpdesk</Link>
        <p className="admin-eyebrow">HUMAN REVIEW</p>
        <h1>Review ticket</h1>
        <code>{ticketId}</code>
        {error ? (
          <p className="admin-error ticket-status-message">{error}</p>
        ) : ticket?.status === "answered" ? (
          <div className="ticket-resolution">
            <span className="ticket-status status-answered">Answered</span>
            <h2>Reviewed answer</h2>
            <p>{ticket.resolution}</p>
          </div>
        ) : ticket?.status === "closed" ? (
          <p className="ticket-status-message">
            This review ticket has been closed without a published answer.
          </p>
        ) : (
          <p className="ticket-status-message">
            {ticket?.status === "claimed"
              ? "An admin is reviewing your question."
              : "Your question is waiting for human review."}
            {" "}This page will update automatically.
          </p>
        )}
      </section>
    </main>
  );
}
