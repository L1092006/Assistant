# Assistant

An experimental, real-time AI secretary ("Alice") that runs as a **continuous agent loop** instead of a request/response chatbot.

On every turn the agent receives its whole (windowed) conversation as context and decides what to do: **reply** to the user, **think** privately, **wait** for new input, or **use a tool**, including controlling the Windows desktop through an MCP server. Replies stream token by token into a Gradio chat UI.

> **Status:** early prototype under active development. Expect rough edges, `FIXME`s and stubbed modules.

## Features

- **Always-on agent loop.** The agent is re-invoked continuously and paces itself with `think` and `wait` tools (`wait` returns early as soon as new input arrives), built on the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python).
- **Model-agnostic.** Works with any OpenAI-compatible endpoint: a local model through [Ollama](https://ollama.com) or a hosted one through OpenRouter.
- **Streaming chat UI.** A Gradio chat that polls the agent's output stream and renders replies as they are generated.
- **Pluggable I/O sources.** Inputs and outputs are abstract sources (with per-source "attention" levels and in-use flags) collected in hubs, so new channels can be added next to the Gradio chat.
- **Context-window management.** A rolling message window with separate token and file (image) budgets. When it overflows, the oldest messages are summarized by an LLM with structured (Pydantic) outputs; when the summary itself grows too long, it is compacted and the omitted details are stored as memory chunks in a ChromaDB vector store.
- **Persistence.** Every message is stored per agent in SQLite behind an abstract SQL client (a MySQL backend is planned).
- **Desktop control.** A Windows MCP server ([windows-mcp](https://pypi.org/project/windows-mcp/)) gives the agent screenshot and input tools.
- **Persona-driven.** The persona and system prompts are configured in `personas.json` and `prompts.py`.

## Architecture

```
            ┌─────────────┐  user messages   ┌───────────────────────────────┐
 Gradio UI ─┤ InputSource ├─────────────────►│ Context                       │
            └─────────────┘                  │  ├─ MessageList (window +     │
                                             │  │   LLM summary)             │
            ┌──────────────┐ streamed text   │  │   ├─ SQLiteClient (history)│
 Gradio UI ◄┤ OutputSource ├◄────────────────┤  │   └─ MemoryClient (Chroma) │
            └──────────────┘                 │  └─ Input/Output source hubs  │
                                             └──────────────┬────────────────┘
                                                            │ one combined context message per turn
                                             ┌──────────────▼────────────────┐
                                             │ Assistant loop                │
                                             │  Agent (think, wait, MCP)     │
                                             └───────────────────────────────┘
```

| File | Role |
|---|---|
| `main.py` | Entry point: builds the `Assistant` and starts the loop. |
| `assistant.py` | The agent loop, the `think`/`wait` tools, the MCP server and output streaming. |
| `context.py` | Conversation state: builds the single context message for each turn and routes output. |
| `MessageList.py` | Rolling message window, summarization and memory offloading. |
| `sources.py` | Input/output source abstractions, hubs and the Gradio chat UI. |
| `sql_database/` | SQL client abstraction, the SQLite implementation and the schema. |
| `memory.py` | ChromaDB + sentence-transformers memory store. |
| `prompts.py`, `personas.json` | System prompts and the persona. |
| `tests/` | pytest suites for the sources, the SQLite client and the message list. |

## Getting started

Requirements: Windows (for the desktop-control MCP server), Python 3.12+, [uv](https://docs.astral.sh/uv/), and either Ollama with a local model or an API key for an OpenAI-compatible provider.

```bash
uv sync
```

Create a `.env` file in the project root:

```dotenv
DB_PATH=sql_database/assistant.db
# For Ollama use http://localhost:11434/v1
PROVIDER_URL=https://openrouter.ai/api/v1
API_KEY=<your key>
MODEL=<model name>
```

Pass the same provider settings to `Assistant(model=..., url=..., api_key=...)` in `main.py` (by default it uses Ollama at `http://localhost:11434/v1`), then run from the project root:

```bash
uv run main.py
```

The chat UI opens on Gradio's local URL. The first start downloads the embedding model (`jinaai/jina-embeddings-v5-text-small`) from Hugging Face.

## Tests

```bash
uv run python -m pytest tests/
```

The LLM, the database and the vector store are faked, so the tests need no network or model.

## License

MIT, see [LICENSE](LICENSE).
