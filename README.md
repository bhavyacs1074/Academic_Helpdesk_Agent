# Academic Helpdesk Agent

## Run the API

Start Ollama with the model configured in `agents/simple-agent.py`, then start
the FastAPI server from the repository root:

```bash
python agents/simple-agent.py
```

The API is available at `http://127.0.0.1:8000`. Interactive API docs are at
`http://127.0.0.1:8000/docs`.

Send a message with `POST /chat`:

```json
{
  "message": "Draft an email asking my professor for a sick day."
}
```

The response contains `response`, `user_id`, and `session_id`. Pass the same
`user_id` and returned `session_id` in a later request to continue that
conversation. Sessions are held in memory and are lost when the server stops.
