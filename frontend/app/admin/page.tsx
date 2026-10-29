"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { LockKeyhole, RefreshCw, ShieldCheck } from "lucide-react";
import {
  ReviewTicket,
  useAdminStore,
} from "../../lib/admin-store";

const API_BASE =
  (process.env.NEXT_PUBLIC_ADMIN_API_URL || "http://127.0.0.1:8000").replace(
    /\/+$/,
    "",
  );
const TOKEN_STORAGE_KEY = "academic-helpdesk-admin-token";

async function adminRequest<T>(
  path: string,
  token: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(body?.detail || `Admin request failed (${response.status}).`);
  }
  return (await response.json()) as T;
}

export default function AdminPage() {
  const token = useAdminStore((state) => state.token);
  const tickets = useAdminStore((state) => state.tickets);
  const loading = useAdminStore((state) => state.loading);
  const error = useAdminStore((state) => state.error);
  const socketConnected = useAdminStore((state) => state.socketConnected);
  const setToken = useAdminStore((state) => state.setToken);
  const setTickets = useAdminStore((state) => state.setTickets);
  const setLoading = useAdminStore((state) => state.setLoading);
  const setError = useAdminStore((state) => state.setError);
  const setSocketConnected = useAdminStore((state) => state.setSocketConnected);
  const clear = useAdminStore((state) => state.clear);
  const [tokenInput, setTokenInput] = useState("");
  const [filter, setFilter] = useState("open");
  const [selectedId, setSelectedId] = useState("");
  const [answer, setAnswer] = useState("");

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const query = filter === "all" ? "" : `?status=${filter}`;
      const result = await adminRequest<ReviewTicket[]>(
        `/admin/tickets${query}`,
        token,
      );
      setTickets(result);
      setError("");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load review tickets.",
      );
    } finally {
      setLoading(false);
    }
  }, [filter, setError, setLoading, setTickets, token]);

  useEffect(() => {
    const savedToken = window.sessionStorage.getItem(TOKEN_STORAGE_KEY);
    if (savedToken) setToken(savedToken);
  }, [setToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!token) return;
    let active = true;
    let retryTimer: ReturnType<typeof setTimeout>;
    let socket: WebSocket;
    const connect = () => {
      if (!active) return;
      const latestSequence = Math.max(
        0,
        ...useAdminStore.getState().tickets.map((ticket) => ticket.event_sequence),
      );
      const socketUrl = `${API_BASE.replace(/^http/, "ws")}/admin/ws`;
      socket = new WebSocket(socketUrl);
      socket.onopen = () => {
        setSocketConnected(true);
        socket.send(
          JSON.stringify({ token, after_sequence: latestSequence }),
        );
      };
      socket.onmessage = () => {
        void refresh();
      };
      socket.onclose = () => {
        setSocketConnected(false);
        if (active) retryTimer = setTimeout(connect, 3000);
      };
      socket.onerror = () => socket.close();
    };
    connect();
    return () => {
      active = false;
      clearTimeout(retryTimer);
      socket?.close();
      setSocketConnected(false);
    };
  }, [refresh, setSocketConnected, token]);

  const selectedTicket = useMemo(
    () => tickets.find((ticket) => ticket.ticket_id === selectedId) ?? null,
    [selectedId, tickets],
  );

  async function submitToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextToken = tokenInput.trim();
    if (!nextToken) return;
    window.sessionStorage.setItem(TOKEN_STORAGE_KEY, nextToken);
    setToken(nextToken);
    setTokenInput("");
  }

  async function claim(ticket: ReviewTicket) {
    try {
      await adminRequest<ReviewTicket>(
        `/admin/tickets/${ticket.ticket_id}/claim`,
        token,
        { method: "POST" },
      );
      setSelectedId(ticket.ticket_id);
      if (filter === "claimed") {
        await refresh();
      } else {
        setFilter("claimed");
      }
      setError("");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Claim failed.",
      );
    }
  }

  async function close(ticket: ReviewTicket) {
    try {
      await adminRequest<ReviewTicket>(
        `/admin/tickets/${ticket.ticket_id}/close`,
        token,
        { method: "POST" },
      );
      await refresh();
      setError("");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Close failed.",
      );
    }
  }

  async function refreshRetriever() {
    try {
      await adminRequest<{ status: string }>(
        "/admin/retriever/refresh",
        token,
        { method: "POST" },
      );
      setError("");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not refresh retrieval cache.",
      );
    }
  }

  async function publish(ticket: ReviewTicket) {
    try {
      await adminRequest<ReviewTicket>(
        `/admin/tickets/${ticket.ticket_id}/publish`,
        token,
        { method: "POST" },
      );
      await refresh();
      setError("");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not publish FAQ entry.",
      );
    }
  }

  async function resolve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTicket || !answer.trim()) return;
    try {
      await adminRequest<ReviewTicket>(
        `/admin/tickets/${selectedTicket.ticket_id}/resolve`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ answer: answer.trim() }),
        },
      );
      setAnswer("");
      setSelectedId(selectedTicket.ticket_id);
      setFilter("answered");
      await refresh();
      setError("");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not resolve ticket.",
      );
    }
  }

  function signOut() {
    window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    clear();
  }

  if (!token) {
    return (
      <main className="admin-login-shell">
        <form className="admin-login-card" onSubmit={submitToken}>
          <div className="admin-brand-icon"><LockKeyhole size={21} /></div>
          <h1>Helpdesk admin</h1>
          <p>Enter the server-configured admin token to access review tickets.</p>
          <label htmlFor="admin-token">Admin token</label>
          <input
            id="admin-token"
            type="password"
            autoComplete="current-password"
            value={tokenInput}
            onChange={(event) => setTokenInput(event.target.value)}
            required
          />
          {error && <p className="admin-error">{error}</p>}
          <button className="admin-primary-button" type="submit">Continue</button>
        </form>
      </main>
    );
  }

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <div>
          <div className="admin-eyebrow"><ShieldCheck size={15} /> REVIEW CONSOLE</div>
          <h1>Unanswered questions</h1>
          <p>Review and resolve questions the academic sources could not verify.</p>
        </div>
        <div className="admin-header-actions">
          <span className={`admin-connection ${socketConnected ? "connected" : ""}`}>
            <i /> {socketConnected ? "Live updates on" : "Reconnecting"}
          </span>
          <button className="admin-secondary-button" onClick={() => void refresh()}>
            <RefreshCw size={15} /> Refresh
          </button>
          <button className="admin-secondary-button" onClick={() => void refreshRetriever()}>
            Reload retrieval cache
          </button>
          <button className="admin-link-button" onClick={signOut}>Sign out</button>
        </div>
      </header>

      <section className="admin-toolbar">
        <div className="admin-filter-tabs">
          {["open", "claimed", "answered", "all"].map((status) => (
            <button
              key={status}
              className={filter === status ? "active" : ""}
              onClick={() => setFilter(status)}
            >
              {status[0].toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>
        <span>{loading ? "Updating…" : `${tickets.length} tickets`}</span>
      </section>

      {error && <p className="admin-error admin-banner">{error}</p>}
      <div className="admin-workspace">
        <section className="ticket-list" aria-label="Review tickets">
          {tickets.length === 0 && !loading ? (
            <div className="admin-empty">No tickets in this view.</div>
          ) : tickets.map((ticket) => (
            <button
              key={ticket.ticket_id}
              className={`ticket-card ${selectedId === ticket.ticket_id ? "selected" : ""}`}
              onClick={() => {
                setSelectedId(ticket.ticket_id);
                setAnswer(ticket.resolution ?? "");
              }}
            >
              <span className="ticket-card-top">
                <span className={`ticket-status status-${ticket.status}`}>{ticket.status}</span>
                <time>{new Date(ticket.last_seen_at).toLocaleString()}</time>
              </span>
              <strong>{ticket.question}</strong>
              <span className="ticket-card-bottom">
                <span>{ticket.occurrence_count} occurrence{ticket.occurrence_count === 1 ? "" : "s"}</span>
                <span>#{ticket.ticket_id.slice(0, 8)}</span>
              </span>
            </button>
          ))}
        </section>

        <section className="ticket-detail">
          {selectedTicket ? (
            <>
              <div className="ticket-detail-heading">
                <div>
                  <span className={`ticket-status status-${selectedTicket.status}`}>{selectedTicket.status}</span>
                  <h2>Question details</h2>
                </div>
                <div className="ticket-detail-actions">
                  {selectedTicket.status === "open" && (
                    <button className="admin-secondary-button" onClick={() => void claim(selectedTicket)}>
                      Claim ticket
                    </button>
                  )}
                  {["open", "claimed"].includes(selectedTicket.status) && (
                    <button className="admin-link-button" onClick={() => void close(selectedTicket)}>
                      Close
                    </button>
                  )}
                </div>
              </div>
              <h3>Student question</h3>
              <p className="ticket-question">{selectedTicket.question}</p>
              <p className="ticket-reason">{selectedTicket.reason}</p>
              {selectedTicket.evidence.length > 0 && (
                <div className="ticket-evidence">
                  <h3>Evidence and source citations</h3>
                  {selectedTicket.evidence.map((item, index) => (
                    <p key={`${item.citation}-${index}`}>
                      {item.summary || item.citation}
                      {typeof item.similarity === "number" &&
                        ` · similarity ${item.similarity.toFixed(3)}`}
                    </p>
                  ))}
                </div>
              )}
              {selectedTicket.resolution ? (
                <div className="ticket-resolution">
                  <h3>Human answer</h3>
                  <p>{selectedTicket.resolution}</p>
                  {selectedTicket.published_at ? (
                    <small>Published to FAQ</small>
                  ) : (
                    <button
                      className="admin-secondary-button"
                      onClick={() => void publish(selectedTicket)}
                    >
                      Publish reviewed answer to FAQ
                    </button>
                  )}
                </div>
              ) : (
                <form className="ticket-answer-form" onSubmit={resolve}>
                  <label htmlFor="admin-answer">Reviewed answer</label>
                  <textarea
                    id="admin-answer"
                    rows={7}
                    value={answer}
                    onChange={(event) => setAnswer(event.target.value)}
                    required
                  />
                  <button className="admin-primary-button" disabled={!answer.trim()}>
                    Save answer
                  </button>
                </form>
              )}
            </>
          ) : (
            <div className="admin-empty admin-detail-empty">Select a ticket to review it.</div>
          )}
        </section>
      </div>
    </main>
  );
}
