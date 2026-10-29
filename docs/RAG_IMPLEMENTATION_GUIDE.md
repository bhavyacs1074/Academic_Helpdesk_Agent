# Retrieval and Human Review

The application uses a local Chroma collection to ground academic answers.
Queries that cannot be supported by retrieved sources create persistent
human-review tickets. For setup commands and API details, see the
[README](../README.md).

## Request flow

```text
Student question
      |
      v
ADK orchestrator -> schedule/policy specialist -> retrieve_academic_evidence
                                                    |
                           relevant evidence ------+------ no evidence
                                 |                         |
                                 v                         v
                     source-grounded answer        SQLite review ticket
                                                           |
                                      authenticated admin REST + WebSocket
                                                           |
                                         reviewed answer -> optional FAQ.md
                                                           |
                                             ingest_pdfs.py -> Chroma
```

The orchestrator and schedule/policy specialists have the retrieval tool
registered in their respective agent modules. Agent instructions require
source-backed answers and prohibit guessing after an abstention. Retrieval
abstention is not a guarantee against every unsupported model statement: the
model can still err, especially if it does not call the retrieval tool.

## Retrieval behavior

[`agents/retrieval.py`](../agents/retrieval.py) performs hybrid semantic and
keyword retrieval against the collection configured by
[`scripts/rag.py`](../scripts/rag.py). Evidence includes the extracted text,
source citation, page/row/chunk location, and relevance metadata. Configure
`RAG_MIN_SIMILARITY` to tune the semantic floor only after checking test
questions against the actual course and policy documents.

The empty-index case is an abstention, not a server exception. It creates a
review ticket without attempting to embed the query. A query with no retrieved
evidence also creates a ticket in `.local/review_tickets.db`; exact normalized
duplicates update the open/claimed ticket's occurrence count.

Try a direct search from the repository root:

```bash
./venv/bin/python - <<'PY'
from agents.retrieval import retrieve

result = retrieve("What are the attendance requirements?")
print("Evidence found:", result["has_evidence"])
for item in result["evidence"]:
    print(item["citation"], item["text"][:300])
if "review_ticket" in result:
    print("Human review ticket:", result["review_ticket"]["ticket_id"])
PY
```

The separate CLI implementation in `scripts/retrieval.py` uses the same review
ticket store. Use `--no-log-unanswered` for a diagnostic query that should not
create a ticket.

## Ingestion and index refresh

[`scripts/ingest_pdfs.py`](../scripts/ingest_pdfs.py) recursively processes PDF,
Markdown, and CSV source files in `data/`. The `data/FAQ.md` file is treated as
an ordinary Markdown source. Only answers an admin has reviewed should be
published there.

Run ingestion after changing source files:

```bash
./venv/bin/python scripts/ingest_pdfs.py
```

Stable source/chunk IDs are upserted, and stale chunks are removed for source
files that were successfully parsed or have been deleted. If a source file
fails to parse, its previous indexed chunks are retained rather than deleted.
After ingestion, use **Reload retrieval cache** in `/admin`, call the protected
`POST /admin/retriever/refresh` endpoint, or restart the API process. FAQ
publication from the admin UI clears the current process's retriever cache.

## Human review

Configure `ADMIN_API_TOKEN` in the backend environment to enable the review
console. The frontend at `/admin` uses REST for durable state and a WebSocket
for live notifications. The WebSocket is only a notification mechanism:
admins should reload the REST ticket list after connecting or reconnecting.
Students can follow the ticket link shown in chat; its status page polls
`GET /tickets/{ticket_id}` until the answer is available.

The current local prototype uses one shared bearer token and unguessable UUID
ticket IDs. It does not provide per-admin accounts, role-based authorization,
rate limiting, or ticket retention controls. Add those before deploying with
real student data.

## Verification checklist

- Confirm a known policy/course question retrieves relevant passages and
  correct citations.
- Confirm an absent question creates an `open` ticket and the agent refers to
  it rather than inventing a source-backed answer.
- Confirm an empty Chroma index also creates a ticket without requiring Ollama
  embeddings for that query.
- Confirm ticket persistence across API restarts and deduplication for
  normalized repeated questions.
- Confirm admin authentication, claim/resolve operations, WebSocket reconnect,
  student follow-up, and optional FAQ publication.
- Re-ingest after publishing an FAQ and verify the source is retrievable after
  refreshing the process cache.
