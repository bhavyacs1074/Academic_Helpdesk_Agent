# Academic Helpdesk Agent

An academic support chatbot with a web interface, a FastAPI backend, and a
multi-agent assistant powered locally by Ollama. A separate ingestion script
indexes academic PDFs, Markdown files, and CSVs in a persistent Chroma database.

> **Project status:** The chat UI, API, agent hierarchy, and document ingestion
> pipeline are present. Connecting Chroma retrieval to the agents is planned;
> indexed documents are not yet automatically used to ground chat responses.

## Contents

- [Features](#features)
- [Technology stack](#technology-stack)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Getting started](#getting-started)
- [Running document ingestion](#running-document-ingestion)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Current limitations](#current-limitations)
- [Roadmap](#roadmap)
- [RAG implementation guide](#rag-implementation-guide)

## Features

### Chat application

- Next.js chat interface with a dark theme, responsive sidebar, animated
  transitions, and a Lottie assistant animation.
- Suggested prompts for academic regulations, course information, and email
  drafting.
- Message composer with Enter-to-send and Shift+Enter for a new line.
- FastAPI `POST /chat` endpoint with input validation and explicit error
  responses.
- FastAPI `POST /chat/stream` endpoint streams answer text and safe progress
  statuses to the web UI using Server-Sent Events.
- Local-development CORS access for the frontend at `localhost:3000` and
  `127.0.0.1:3000`.
- ADK conversation history is saved in a local SQLite database and reused for
  follow-up turns in the same browser tab.

### Agent workflow

- An orchestrator agent routes relevant requests to specialized agents:
  - **Policy agent** — academic policies, procedures, and regulations.
  - **Schedule agent** — course planning, schedules, and time management.
  - **Email agent** — drafting, editing, and responding to academic emails.
- General in-scope academic questions can be handled by the orchestrator.
- Agent models are configured through LiteLLM and use the local
  `gemma4:e4b` model served by Ollama.

### Academic document indexing

- Recursively scans the `data/` directory for `.pdf`, `.md`, and `.csv` files.
- Extracts PDF text page-by-page with `pypdf`, reads Markdown as UTF-8, and
  converts CSV rows into labeled field/value text.
- Splits extracted text into overlapping word chunks and stores each chunk with
  source and location metadata in the persistent Chroma collection
  `academic_documents`.
- Uses stable SHA-256 IDs and Chroma `upsert`, so re-running ingestion updates
  existing chunk IDs rather than inserting duplicate IDs.

## Technology stack

| Area | Technologies |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript |
| UI | Tailwind CSS 4, Framer Motion, Lucide React, Lottie |
| API | Python, FastAPI, Pydantic, Uvicorn |
| Agent framework | Google Agent Development Kit (ADK) |
| Model routing | LiteLLM |
| Local model runtime | Ollama (`gemma4:e4b`) |
| Document processing | pypdf, Python `csv` module |
| Vector storage | ChromaDB with persistent local storage |

Python package versions are pinned in [`requirements.txt`](./requirements.txt);
frontend dependencies and scripts are defined in
[`frontend/package.json`](./frontend/package.json).

## Architecture

```text
Browser
  └── Next.js frontend
        └── POST /chat ──> FastAPI server
                              └── ADK orchestrator
                                    ├── Policy agent
                                    ├── Schedule agent
                                    └── Email agent
                                          └── LiteLLM ──> Ollama model

data/ ──> scripts/ingest_pdfs.py ──> ChromaDB (chroma_db/)
                                      └── Retrieval integration: planned
```

The frontend keeps the active `session_id` in tab-scoped `sessionStorage` and
sends it with every turn. ADK stores the associated conversation events in
`.local/agent_sessions.db`, so history survives API process restarts. The
**New conversation** button creates a fresh session. The transcript UI itself
does not restore prior messages after a page refresh, even though the model can
still use the stored session context.

This is conversation history, not permanent learned memory: the model does not
learn facts from one session for use in unrelated sessions. Session data has no
automatic expiry or deletion UI. The local prototype also has no
authentication, so it should not be exposed publicly with sensitive
conversations without access controls and a data-retention policy.

## Requirements

- Python with support for the pinned packages in `requirements.txt`.
- Node.js and npm.
- [Ollama](https://ollama.com/) installed and running locally.
- The configured Ollama model pulled locally:

  ```bash
  ollama pull gemma4:e4b
  ```

The Python agent uses `http://localhost:11434` for Ollama. Its model and endpoint
are set in [`agents/model_config.py`](./agents/model_config.py).

## Getting started

### 1. Install Python dependencies

From the repository root:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If you already created the project virtual environment, activate it and install
or update packages with the last command.

### 2. Start Ollama

Make sure the Ollama service is running and `gemma4:e4b` is available. If Ollama
is not already running as a service, start it in a separate terminal:

```bash
ollama serve
```

### 3. Start the API server

From the repository root:

```bash
./venv/bin/python server.py
```

The API listens at `http://127.0.0.1:8000`. Interactive Swagger docs are
available at [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs).

### 4. Configure and start the frontend

Create `frontend/.env.local` with the API endpoint:

```dotenv
NEXT_PUBLIC_CHAT_API_URL=http://127.0.0.1:8000/chat
```

Then run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open [`http://localhost:3000`](http://localhost:3000). Restart the Next.js
development server after changing the environment file. Keep machine-specific
settings out of commits. Values prefixed with `NEXT_PUBLIC_` are exposed to
browser-side code and must not contain secrets.

## Running document ingestion

Place supported academic source files anywhere under `data/`. The repository
already organizes examples under folders such as `data/policies/`,
`data/course_details/`, `data/curriculum/`, `data/faculty/`, and
`data/timetable/`.

Run the ingestion script from the repository root:

```bash
./venv/bin/python scripts/ingest_pdfs.py
```

The script recursively scans `data/` and indexes:

- **PDF:** text is extracted for each page. Scanned image-only pages need OCR
  and will not produce searchable text through the current parser.
- **Markdown:** UTF-8 text is chunked directly.
- **CSV:** each row is represented as `column: value` lines, preserving the
  relationship between headers and values.

Chunks are stored in the `academic_documents` collection under `chroma_db/`.
Metadata includes the relative source path, file type, chunk number, and
page/row location where applicable. Chroma uses its default embedding function
unless configured otherwise; its model may need to be downloaded the first time
the collection is populated.

Ingestion is a separate command-line step. The chat agent does not currently
query the collection, so running ingestion alone does not make chat answers
document-grounded.

## API reference

### `POST /chat`

Request JSON:

```json
{
  "message": "What are the attendance requirements?",
  "user_id": "student-123",
  "session_id": "optional-existing-session-id"
}
```

Only `message` is required. It must contain non-whitespace text and be no longer
than 4,000 characters. If `session_id` is omitted, the API creates one.

Example:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Draft an email asking my professor for a sick day."}'
```

Successful response:

```json
{
  "response": "Subject: Request for Sick Leave ...",
  "user_id": "default_user",
  "session_id": "returned-session-id"
}
```

Invalid input receives a validation error. Agent/model processing failures are
returned as HTTP 502 responses.

### `POST /chat/stream`

Accepts the same JSON body as `/chat`, and returns a Server-Sent Events stream
with `status`, `delta`, `done`, and `error` events. The frontend displays answer
text as it arrives and shows safe progress updates such as document search.
Private model reasoning is not sent to clients.

## Project structure

```text
.
├── agents/
│   ├── academic_agent.py   # Orchestrator, ADK runner, and run_agent()
│   ├── email_agent.py      # Email specialist
│   ├── model_config.py     # Shared Ollama/LiteLLM configuration
│   ├── policy_agent.py     # Policy specialist
│   └── schedule_agent.py   # Scheduling specialist
├── .local/                 # Git-ignored SQLite conversation history
├── data/                   # Source PDFs, Markdown, and CSV files
├── frontend/
│   ├── app/                # Next.js UI and styles
│   └── public/             # Static assets and animation
├── scripts/
│   └── ingest_pdfs.py      # Document parsing and Chroma ingestion
├── chroma_db/              # Persistent Chroma database
├── requirements.txt        # Pinned Python dependencies
└── server.py               # FastAPI application
```

## Current limitations

- Chroma ingestion and chat are not connected yet; responses are not grounded
  in indexed documents and do not cite sources.
- The transcript display is not restored after a page refresh, though ADK
  retains the session context while the tab's session ID is available.
- Stored conversation sessions do not yet have automatic expiry, deletion
  controls, or authenticated per-user access.
- The PDF parser extracts embedded text only; scanned documents need OCR.
- CORS is configured for local development origins. A deployed frontend needs
  its origin configured explicitly.
- Authentication, authorization, rate limiting, and production deployment
  configuration are not implemented.

## Roadmap

These are planned areas of work, not features currently delivered:

- [ ] Connect Chroma similarity search to the agent workflow (retrieval-
  augmented generation; see the [RAG implementation guide](./docs/RAG_IMPLEMENTATION_GUIDE.md)).
- [ ] Include source filenames and PDF page numbers in answers; add citations
  and a way to inspect supporting passages.
- [ ] Restore and display prior messages when resuming an existing session.
- [ ] Add session deletion/retention controls and authenticated user identity.
- [ ] Add OCR support for scanned PDFs and improve parsing of complex tables.
- [ ] Make ingestion incremental, remove stale chunks after source changes,
  and report per-file indexing results.
- [ ] Add automated tests for API behavior, agent routing, ingestion, and
  retrieval quality.
- [ ] Add production configuration for secrets, CORS origins, logging,
  monitoring, authentication, and deployment.

## License

See [`LICENSE`](./LICENSE).

## RAG implementation guide

For a step-by-step plan to connect Chroma retrieval to ADK agent tools, see the
[RAG implementation guide](./docs/RAG_IMPLEMENTATION_GUIDE.md). It documents
the current collection and metadata, proposes a retriever function, explains
how to expose it to the relevant agents, and includes a testing checklist.
