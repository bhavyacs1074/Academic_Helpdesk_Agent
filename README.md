# Academic Helpdesk Agent

A local academic helpdesk with a Next.js chat interface, a FastAPI backend, and Google ADK agents. It uses Ollama for language generation and embeddings, ChromaDB for document retrieval, and a SQLite queue for questions that need human review.

The app is designed to answer questions from the academic material in `data/`, look up some course records, draft academic emails, cite its sources, and refer unanswered questions for review. It does not send emails.

## What’s included

- A Next.js chat interface and FastAPI API.
- An ADK orchestrator with policy, schedule, and email specialist agents.
- RAG over PDF, Markdown, and CSV files, with source metadata for citations.
- Course lookup and course counting tools in `tools/academic_tools.py`.
- A human review queue with an admin interface.
- Local SQLite storage for chat sessions and review tickets.

The orchestrator is an LLM agent instructed to transfer requests to the appropriate specialist. Routing is guided by its instructions; it is not a deterministic keyword router.

## Architecture

```text
Browser
  └── Next.js frontend
        └── FastAPI API
              └── ADK helpdesk orchestrator
                    ├── Policy agent
                    ├── Schedule agent
                    └── Email agent
                          └── Ollama / LiteLLM

data/
  └── scripts/ingest_pdfs.py
        └── ChromaDB
              └── agents/retrieval.py
                    └── review tickets when evidence is insufficient
```

### Project layout

| Path | Purpose |
| --- | --- |
| `agents/` | Orchestrator, specialist agents, retrieval, model configuration, and review-ticket handling |
| `tools/academic_tools.py` | Structured course lookup and course counting |
| `data/` | Academic source material |
| `scripts/ingest_pdfs.py` | Reads source documents and indexes them in ChromaDB |
| `scripts/retrieval.py` | Command-line document search |
| `server.py` | FastAPI application |
| `frontend/` | Next.js user interface |
| `tests/` | Unit tests for retrieval escalation, admin API, and review tickets |

## Requirements

- Python 3.12 is a suitable choice for this project’s pinned dependencies.
- Node.js 20.9 or later and npm. Next.js lists Node.js 20.9 as its minimum version in the [installation documentation](https://nextjs.org/docs/app/getting-started/installation).
- Ollama installed and running locally. Use the [official Ollama download page](https://ollama.com/download).
- Disk space and available memory for the local models. Ollama lists the configured `gemma4:e4b` model at roughly 6.6–9.5 GB; actual runtime memory use varies by setup ([model details](https://ollama.com/library/gemma4/tags)).
- The files in `requirements.txt` and `frontend/package-lock.json`.

The chat model and endpoint are currently set in `agents/model_config.py` to `gemma4:e4b` at `http://localhost:11434`. The embedding model defaults to `nomic-embed-text` in `scripts/rag.py`; its Ollama page documents the model and pull command ([model details](https://ollama.com/library/nomic-embed-text)).

## Setup

Install Python, Node.js, and Ollama using the instructions for your operating system. The following Bash script installs the project’s Python and frontend dependencies and downloads the two Ollama models. Run it from the repository root **after starting Ollama**. It does not install system-level Python, Node.js, or Ollama.

```bash
#!/usr/bin/env bash
set -euo pipefail

for command_name in python3 node npm ollama; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name"
    exit 1
  fi
done

node -e '
  const [major, minor] = process.versions.node.split(".").map(Number);
  if (major < 20 || (major === 20 && minor < 9)) {
    console.error("Node.js 20.9 or later is required.");
    process.exit(1);
  }
'

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm --prefix frontend ci

ollama pull gemma4:e4b
ollama pull nomic-embed-text

echo "Setup complete."
```

If Ollama is not already running as a service, start it in a separate terminal:

```bash
ollama serve
```

Alternatively, install the dependencies manually from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cd frontend
npm ci
cd ..
```

Then pull the models:

```bash
ollama pull gemma4:e4b
ollama pull nomic-embed-text
```

## Index the academic documents

Run ingestion from the repository root after Ollama is available:

```bash
source .venv/bin/activate
python scripts/ingest_pdfs.py
```

The script searches `data/` recursively for CSV, Markdown, and PDF files. It extracts PDF text with `pypdf`, reads Markdown as UTF-8, and turns CSV rows into text. PDF pages that contain only scanned images are not searchable because OCR is not implemented.

The index is stored in `chroma_db/`, which the script creates as needed. The default collection is `academic_documents_nomic_embed_text`. You do not need to create the directory in advance.

Ingestion uses Ollama embeddings and upserts chunks with stable IDs. Let it finish; if you interrupt it, run it again to complete indexing. After ingesting while the API is running, restart the API or use the admin page’s **Reload retrieval cache** action.

## Run the application

Start the backend in one terminal from the repository root:

```bash
source .venv/bin/activate
python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

The interactive API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Create `frontend/.env.local` with:

```dotenv
NEXT_PUBLIC_CHAT_API_URL=http://127.0.0.1:8000/chat
NEXT_PUBLIC_ADMIN_API_URL=http://127.0.0.1:8000
```

The chat URL is important: without it, the frontend defaults to `/api/chat`, for which this repository does not provide a Next.js API route. These `NEXT_PUBLIC_` values are visible to browser code, so do not put secrets in them. Restart the frontend after changing the file.

Start the frontend in another terminal:

```bash
cd frontend
npm run dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

## Run with Docker Compose

The repository includes a Python API image, a Next.js frontend image, and a Compose configuration that connects them to Ollama. Install Docker Engine or Docker Desktop with the Compose plugin, then run these commands from the repository root.

Build both application images and start the Ollama service:

```bash
docker compose build
docker compose up -d ollama
```

Download the chat and embedding models into the persistent Ollama volume:

```bash
docker compose exec ollama ollama pull gemma4:e4b
docker compose exec ollama ollama pull nomic-embed-text
```

Index the bundled academic files, then start the API and frontend:

```bash
docker compose run --rm ingest
docker compose up -d backend frontend
```

Open [http://localhost:3000](http://localhost:3000). The API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs). The default port mappings bind to the local machine only.

The Ollama service uses the official [Ollama Docker image](https://github.com/ollama/ollama/blob/main/docs/docker.mdx). GPU access is not configured by default; configure the Ollama service for the hardware and container runtime available on the deployment host.

Compose stores Ollama models, academic data, ChromaDB, and application sessions in named volumes. These survive `docker compose down`; `docker compose down -v` removes them. The academic-data volume is initially populated from the files included in the API image. If you add or replace source files after that volume has been initialized, update the volume and rerun ingestion so the new files enter the index.

To enable admin review, set the token in the shell before starting the backend:

```bash
export ADMIN_API_TOKEN="replace-with-a-long-random-secret"
docker compose up -d backend frontend
```

For a deployment with a public domain, build the frontend with API URLs that the user's browser can reach. These values are embedded in the frontend at build time; `http://backend:8000` is only resolvable between containers and is not suitable for browser requests.

```bash
export NEXT_PUBLIC_CHAT_API_URL="https://api.example.org/chat"
export NEXT_PUBLIC_ADMIN_API_URL="https://api.example.org"
export CORS_ORIGINS="https://helpdesk.example.org"
docker compose build frontend
docker compose up -d backend frontend
```

The Compose file binds ports to localhost for local use. For an internet-facing deployment, place the services behind a configured reverse proxy with TLS, adjust the port exposure, and use an appropriate authentication and access-control setup.

## Human review and admin page

The admin API is disabled unless `ADMIN_API_TOKEN` is set in the environment of the terminal running the backend. For example:

```bash
export ADMIN_API_TOKEN="replace-with-a-long-random-secret"
python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:3000/admin` and enter the same token. Keep it out of source control.

When retrieval cannot find sufficiently relevant evidence, it can create a review ticket. Administrators can list, claim, answer, close, and explicitly publish reviewed answers. Publishing adds the answer to `data/FAQ.md`; run ingestion afterwards to include it in the vector index.

The backend stores chat sessions and tickets in `.local/agent_sessions.db` and `.local/review_tickets.db`. These databases and the Chroma index are generated local data, not source documents.

## API examples

Send a chat request:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the attendance requirement for the Major exam?"}'
```

The response includes `response`, `user_id`, and `session_id`. Include the returned session ID in later requests to continue that conversation.

The streaming endpoint accepts the same request body:

```text
POST /chat/stream
```

It sends Server-Sent Events such as `status`, `delta`, `done`, and `error`.

Admin HTTP endpoints require `Authorization: Bearer <ADMIN_API_TOKEN>`:

| Endpoint | Purpose |
| --- | --- |
| `GET /admin/tickets?status=open` | List tickets, optionally filtered by status |
| `POST /admin/tickets/{ticket_id}/claim` | Claim an open ticket |
| `POST /admin/tickets/{ticket_id}/resolve` | Save a reviewed answer |
| `POST /admin/tickets/{ticket_id}/close` | Close a ticket without an answer |
| `POST /admin/tickets/{ticket_id}/publish` | Publish an answered ticket to `data/FAQ.md` |
| `POST /admin/retriever/refresh` | Clear the backend’s cached retrieval data |
| `GET /tickets/{ticket_id}` | Check ticket status |
| `WS /admin/ws` | Receive live admin ticket notifications |

## Search the index from the command line

After indexing, search directly with:

```bash
source .venv/bin/activate
python scripts/retrieval.py "attendance requirement for the Major exam"
```

The command prints JSON containing retrieved evidence and source metadata. By default, an unanswered query may create a review ticket. Add `--no-log-unanswered` for a search that should not create one:

```bash
python scripts/retrieval.py "example query" --no-log-unanswered
```

## Data and citation behavior

Ingestion records a source path and location metadata, such as a PDF page or CSV row. The retrieval system combines semantic and keyword matching, and agent instructions require citations for evidence-based answers.

The current `data/` directory contains 49 files: 15 Markdown, 6 PDF, and 28 CSV files. The assignment asks for 20–30 real documents. Some CSVs are supporting timetables or tables rather than standalone policy documents, so document which sources count toward the assignment’s collection and record their provenance.

## Tests

The repository includes unit tests for review-ticket storage, admin API behavior, and retrieval escalation. Run them from the repository root with:

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

These tests check software behavior; they are not the assignment’s 20–30-question answer-quality evaluation.

## Known limitations and remaining assignment work

- `count_courses` requires both a department and semester. It supports semester I/II or 1/2, optional academic year, course level, and elective-only filters.
- The course CSV parser looks for a recognizable course-code and course-name header, then applies that header layout to subsequent rows. Timetable CSVs have differing layouts, so some may not be parsed completely. Verify counts and slots against the cited source files, especially for files with repeated headers or unusual column names.
- Out-of-scope refusal is directed by the orchestrator’s instructions; it is not enforced by a separate deterministic classifier.
- The faculty directory is available to document retrieval, but there is no dedicated structured faculty-email lookup tool.
- Email assistance drafts text; it does not send email.
- Scanned PDF OCR is not implemented.
- The assignment’s 20–30 prompt set and findings report are not present as a model-evaluation dataset/report. Add the prompts and evaluate answer accuracy, citation groundedness, correct refusals, and answer changes across repeated runs or models.
- The 16 GB laptop target has not been benchmarked in this repository. Check local memory and disk usage with the chosen Ollama model.

## Environment variables

| Variable | Used by | Default / purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_CHAT_API_URL` | Frontend chat | Set to `http://127.0.0.1:8000/chat` |
| `NEXT_PUBLIC_ADMIN_API_URL` | Frontend admin and ticket pages | `http://127.0.0.1:8000` |
| `ADMIN_API_TOKEN` | Backend admin API | Unset disables admin endpoints |
| `CORS_ORIGINS` | Backend API and admin WebSocket | Comma-separated allowed browser origins |
| `ACADEMIC_CHROMA_DIR` | Ingestion and retrieval scripts | Repository `chroma_db/` directory |
| `OLLAMA_BASE_URL` | Embedding and retrieval scripts | `http://localhost:11434` |
| `OLLAMA_EMBED_MODEL` | Embedding and retrieval scripts | `nomic-embed-text` |
| `OLLAMA_API_BASE` | Chat model client | `http://localhost:11434` |
| `OLLAMA_CHAT_MODEL` | Chat model client | `gemma4:e4b` |

The chat model and chat endpoint are set directly in `agents/model_config.py`; changing the embedding variables does not change those settings.
