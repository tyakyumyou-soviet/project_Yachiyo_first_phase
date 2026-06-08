# Phase 1 Core Agent

Phase 1 is the backend brain for Project Yachiyo. The implementation now includes:

- FastAPI server with `GET /health`
- browser chat UI on `GET /`
- `GET /tools`
- `GET /sessions`
- `POST /sessions/{session_id}/reset`
- `POST /chat` using Server-Sent Events
- `/ws/chat` using WebSocket
- `GET /models` and `POST /models/select` for model switching
- Ollama-first generation with a deterministic development fallback
- XML stream parsing for text, emotion, motion, thinking, plan, and tool packets
- automatic character profile injection from `Features_yachiyo.txt`
- SQLite-backed memory storage
- safe local file tools with approval for destructive actions

## Setup

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Optional Ollama setup:

```powershell
ollama pull gemma3:1b
ollama pull qwen3:1.7b
ollama pull qwen3:4b-instruct-2507-q4_K_M
```

Available runtime profiles:

- `Gemma 3 1B` -> `gemma3:1b`
- `Qwen3 1.7B` -> `qwen3:1.7b`
- `Qwen3 4B Instruct 2507 Q4_K_M` -> `qwen3:4b-instruct-2507-q4_K_M`

## Run

```powershell
.venv\Scripts\python.exe main.py
```

Server address:

- `http://127.0.0.1:8000`
- open the root URL in a browser to use the built-in chat console

## Verify

Automated tests:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_phase1
```

Manual health check:

```powershell
.venv\Scripts\python.exe -c "import httpx; print(httpx.get('http://127.0.0.1:8000/health').json())"
```

Manual SSE check:

```powershell
.venv\Scripts\python.exe -c "import httpx; print(httpx.post('http://127.0.0.1:8000/chat', json={'text':'time please','session_id':'manual'}).text)"
```

Model switching verification:

```powershell
.venv\Scripts\python.exe scripts\verify_model_switching.py
```

Prompt inspection:

```powershell
.venv\Scripts\python.exe scripts\inspect_prompt.py "スマホで送信できない" --json
```

Roleplay evaluation:

```powershell
.venv\Scripts\python.exe scripts\run_roleplay_eval.py --max-cases 1
```

## Notes

- The app tries Ollama first. If Ollama is unreachable and `ENABLE_DEV_FALLBACK=1`, a deterministic fallback response is used.
- The fallback path can issue `get_current_time` and `list_directory` so tool loops can be verified without a live LLM.
- The active Ollama model is switchable from the browser UI and via `POST /models/select`.
- The default active runtime is `Qwen3 1.7B` when no saved model state exists.
- Yachiyo roleplay prompts are built from separate persona, style, scene-state, lore, memory, and final-instruction layers.
- `scripts\inspect_prompt.py` shows the final message stack and prompt section budgets.
- `scripts\run_roleplay_eval.py` runs a lightweight local RoleBench-style evaluation.
- Yachiyo's voice and behavior are loaded from `Features_yachiyo.txt`; `/health` reports whether that profile is loaded.
- Memory is stored in `data/memory.sqlite3`.
- File tools are restricted to the configured workspace root.
