from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from agent.llm_engine import (
    LLMEngineError,
    generate_stream,
    normalize_yachiyo_output,
    ollama_healthcheck,
    ollama_installed_models,
    user_visible_llm_failure_message,
    warmup_ollama,
)
from agent.character_profile import character_profile_stats
from agent.drift_detector import detect_drift, safe_recovery_reply
from agent.memory_hub import MemoryHub
from agent.prompt_builder import build_messages
from agent.stream_parser import strip_residual_control_tags, strip_stage_directions
from config import (
    APP_HOST,
    APP_PORT,
    DATA_DIR,
    OLLAMA_WARMUP_ENABLED,
    SESSION_STORE_PATH,
    TURN_STREAM_TIMEOUT_SECONDS,
)
from model_manager import get_active_profile, list_model_profiles, set_active_profile
from schemas import (
    ChatMessage,
    ChatRequest,
    ControlPacket,
    ModelSelectRequest,
    SessionSnapshot,
    StatusPayload,
    ToolApprovalPayload,
    ToolResultPayload,
)
from tools.hitl_manager import DESTRUCTIVE_TOOLS, request_approval
from tools.tool_registry import get_tool, get_tool_catalog


@dataclass
class ChatSession:
    session_id: str
    history: List[ChatMessage] = field(default_factory=list)
    completed_turns: List[Dict[str, str]] = field(default_factory=list)
    scene_state: Dict[str, str] = field(default_factory=dict)
    delta_summary: str = ""
    drift_events: List[Dict[str, str]] = field(default_factory=list)

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            session_id=self.session_id,
            history_size=len(self.history),
            completed_turns=len(self.completed_turns),
            recent_messages=self.history[-6:],
        )


class SessionStore:
    def __init__(self, storage_path: Path = SESSION_STORE_PATH) -> None:
        self._sessions: Dict[str, ChatSession] = {}
        self._storage_path = Path(storage_path)
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def get_or_create(self, session_id: Optional[str]) -> ChatSession:
        resolved = session_id or str(uuid4())
        if resolved not in self._sessions:
            self._sessions[resolved] = ChatSession(session_id=resolved)
            self._save()
        return self._sessions[resolved]

    def list_sessions(self) -> List[SessionSnapshot]:
        return [session.snapshot() for session in self._sessions.values()]

    def get(self, session_id: str) -> Optional[ChatSession]:
        return self._sessions.get(session_id)

    def reset(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id] = ChatSession(session_id=session_id)
            self._save()

    def save(self) -> None:
        self._save()

    def clear_all(self) -> None:
        self._sessions = {}
        self._save()

    def _save(self) -> None:
        payload = {
            "sessions": [
                {
                    "session_id": session.session_id,
                    "history": [message.model_dump(mode="json") for message in session.history],
                    "completed_turns": list(session.completed_turns),
                    "scene_state": dict(session.scene_state),
                    "delta_summary": session.delta_summary,
                    "drift_events": list(session.drift_events[-20:]),
                }
                for session in self._sessions.values()
            ]
        }
        self._storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except Exception:
            return
        sessions = payload.get("sessions", [])
        if not isinstance(sessions, list):
            return
        restored: Dict[str, ChatSession] = {}
        for item in sessions:
            if not isinstance(item, dict):
                continue
            session_id = str(item.get("session_id", "")).strip()
            if not session_id:
                continue
            history_payload = item.get("history", [])
            completed_turns = item.get("completed_turns", [])
            scene_state = item.get("scene_state", {})
            delta_summary = str(item.get("delta_summary", ""))
            drift_events = item.get("drift_events", [])
            history: List[ChatMessage] = []
            if isinstance(history_payload, list):
                for message in history_payload:
                    try:
                        history.append(ChatMessage.model_validate(message))
                    except Exception:
                        continue
            normalized_turns = []
            if isinstance(completed_turns, list):
                for turn in completed_turns:
                    if isinstance(turn, dict) and "user" in turn and "assistant" in turn:
                        normalized_turns.append({"user": str(turn["user"]), "assistant": str(turn["assistant"])})
            restored[session_id] = ChatSession(
                session_id=session_id,
                history=history,
                completed_turns=normalized_turns,
                scene_state={str(key): str(value) for key, value in scene_state.items()} if isinstance(scene_state, dict) else {},
                delta_summary=delta_summary,
                drift_events=[
                    {str(key): str(value) for key, value in event.items()}
                    for event in drift_events
                    if isinstance(event, dict)
                ]
            )
        self._sessions = restored


memory_hub = MemoryHub()
session_store = SessionStore()


@asynccontextmanager
async def lifespan(_: FastAPI):
    warmup_task: Optional[asyncio.Task] = None
    if OLLAMA_WARMUP_ENABLED:
        warmup_task = asyncio.create_task(_warmup_model_task())
    yield
    if warmup_task is not None and not warmup_task.done():
        warmup_task.cancel()


async def _warmup_model_task() -> None:
    try:
        await warmup_ollama()
    except Exception:
        return


async def _iter_with_timeout(source: AsyncGenerator[str, None], total_seconds: float) -> AsyncGenerator[str, None]:
    deadline = time.monotonic() + total_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError
        try:
            chunk = await asyncio.wait_for(source.__anext__(), timeout=remaining)
        except StopAsyncIteration:
            break
        yield chunk


app = FastAPI(title="Project Yachiyo Phase 1", lifespan=lifespan)


def _app_shell_html() -> str:
    return """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Project Yachiyo Phase 1</title>
  <style>
    :root {
      --bg: #08111f;
      --panel: rgba(12, 24, 41, 0.82);
      --panel-strong: rgba(8, 18, 31, 0.94);
      --line: rgba(212, 175, 55, 0.28);
      --accent: #d4af37;
      --accent-soft: #92c6ff;
      --text: #edf4ff;
      --muted: #9eb1c8;
      --user: #183657;
      --assistant: #14263b;
      --system: #1c2430;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      font-family: "Yu Gothic UI", "Hiragino Sans", sans-serif;
      background:
        radial-gradient(circle at top, rgba(212, 175, 55, 0.16), transparent 28%),
        linear-gradient(180deg, #091321 0%, #050b14 100%);
    }
    .wrap {
      width: min(1100px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      gap: 16px;
      grid-template-columns: 300px 1fr;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.25);
      backdrop-filter: blur(14px);
    }
    .sidebar {
      padding: 18px;
      display: grid;
      gap: 14px;
      align-content: start;
    }
    .title {
      margin: 0;
      font-size: 26px;
      letter-spacing: 0.04em;
    }
    .subtitle {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.06);
      color: var(--accent-soft);
      font-size: 13px;
    }
    .section-title {
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }
    .kv {
      display: grid;
      gap: 8px;
      font-size: 14px;
    }
    .kv div {
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.04);
    }
    .chat {
      min-height: 76vh;
      display: grid;
      grid-template-rows: auto 1fr auto;
      overflow: hidden;
    }
    .chat-head {
      padding: 18px 20px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      background: var(--panel-strong);
    }
    .log {
      padding: 20px;
      display: grid;
      gap: 12px;
      overflow: auto;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.02), transparent 18%),
        transparent;
    }
    .msg {
      padding: 14px 16px;
      border-radius: 16px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
      border: 1px solid rgba(255,255,255,0.06);
    }
    .msg.user { background: var(--user); margin-left: 48px; }
    .msg.assistant { background: var(--assistant); margin-right: 48px; }
    .msg.system { background: var(--system); color: var(--muted); }
    .composer {
      padding: 16px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      display: grid;
      gap: 12px;
      background: var(--panel-strong);
    }
    textarea {
      width: 100%;
      min-height: 96px;
      resize: vertical;
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 14px;
      padding: 14px 16px;
      background: rgba(255,255,255,0.04);
      color: var(--text);
      font: inherit;
    }
    button {
      border: 0;
      border-radius: 14px;
      padding: 12px 18px;
      background: linear-gradient(135deg, var(--accent), #f4d978);
      color: #1b1a14;
      font-weight: 700;
      cursor: pointer;
    }
    button.secondary {
      background: rgba(255,255,255,0.08);
      color: var(--text);
      border: 1px solid rgba(255,255,255,0.08);
    }
    .row {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .status-dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: #e7a44c;
      box-shadow: 0 0 0 5px rgba(231, 164, 76, 0.16);
    }
    .status-dot.ok {
      background: #61d487;
      box-shadow: 0 0 0 5px rgba(97, 212, 135, 0.16);
    }
    .tiny { font-size: 12px; color: var(--muted); }
    @media (max-width: 900px) {
      .wrap { grid-template-columns: 1fr; }
      .chat { min-height: calc(100vh - 48px); }
      .msg.user, .msg.assistant { margin: 0; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <aside class="panel sidebar">
      <div>
        <p class="badge">Phase 1 Runtime</p>
        <h1 class="title">Yachiyo</h1>
        <div class="subtitle">ブラウザからそのまま Phase 1 の会話 API を触れるテスト画面です。</div>
      </div>
      <div>
        <div class="section-title">Status</div>
        <div class="kv">
          <div>App: <span id="app-status">checking...</span></div>
          <div>Ollama: <span id="ollama-status">checking...</span></div>
          <div>Memory: <span id="memory-status">-</span></div>
          <div>Session: <span id="session-id">-</span></div>
        </div>
      </div>
      <div>
        <div class="section-title">Events</div>
        <div class="tiny" id="event-status">起動直後です。</div>
      </div>
      <div class="row">
        <button class="secondary" id="refresh-health" type="button">状態更新</button>
        <button class="secondary" id="reset-session" type="button">セッション初期化</button>
      </div>
    </aside>

    <main class="panel chat">
      <div class="chat-head">
        <div class="row">
          <span class="status-dot" id="status-dot"></span>
          <strong>Chat Console</strong>
        </div>
        <div class="tiny">SSE over <code>/chat</code></div>
      </div>
      <div class="log" id="log"></div>
      <div class="composer">
        <textarea id="prompt" placeholder="メッセージを入力"></textarea>
        <div class="row">
          <button id="send" type="button">送信</button>
          <span class="tiny">Shift+Enterで改行 / Enterで送信</span>
        </div>
      </div>
    </main>
  </div>

  <script>
    const logEl = document.getElementById("log");
    const promptEl = document.getElementById("prompt");
    const sendBtn = document.getElementById("send");
    const refreshBtn = document.getElementById("refresh-health");
    const resetBtn = document.getElementById("reset-session");
    const appStatusEl = document.getElementById("app-status");
    const ollamaStatusEl = document.getElementById("ollama-status");
    const memoryStatusEl = document.getElementById("memory-status");
    const sessionIdEl = document.getElementById("session-id");
    const eventStatusEl = document.getElementById("event-status");
    const statusDotEl = document.getElementById("status-dot");
    const SESSION_KEY = "yachiyo-phase1-session-id";
    let sessionId = localStorage.getItem(SESSION_KEY) || crypto.randomUUID();
    let currentAssistantBubble = null;
    localStorage.setItem(SESSION_KEY, sessionId);
    sessionIdEl.textContent = sessionId;

    function appendMessage(kind, text) {
      const div = document.createElement("div");
      div.className = `msg ${kind}`;
      div.textContent = text;
      logEl.appendChild(div);
      logEl.scrollTop = logEl.scrollHeight;
      return div;
    }

    function setHealth(health) {
      appStatusEl.textContent = health.status;
      ollamaStatusEl.textContent = `${health.ollama.status} (${health.ollama.detail || "-"})`;
      memoryStatusEl.textContent = `${health.memory.semantic_count} semantic / ${health.memory.episode_count} episodic`;
      statusDotEl.classList.toggle("ok", health.ollama.status === "ok");
    }

    async function refreshHealth() {
      try {
        const response = await fetch("/health");
        const health = await response.json();
        setHealth(health);
      } catch (error) {
        appStatusEl.textContent = "error";
        ollamaStatusEl.textContent = String(error);
      }
    }

    function handlePacket(packet) {
      eventStatusEl.textContent = `last event: ${packet.event_type}`;
      if (packet.event_type === "text_chunk") {
        if (!currentAssistantBubble) {
          currentAssistantBubble = appendMessage("assistant", "");
        }
        currentAssistantBubble.textContent += packet.payload;
        logEl.scrollTop = logEl.scrollHeight;
        return;
      }
      if (packet.event_type === "thinking_summary" || packet.event_type === "plan_summary") {
        appendMessage("system", `${packet.event_type}: ${packet.payload}`);
        return;
      }
      if (packet.event_type === "emotion_trigger") {
        appendMessage("system", `emotion: ${packet.payload.emotion_type} (${packet.payload.intensity})`);
        return;
      }
      if (packet.event_type === "motion_trigger") {
        appendMessage("system", `motion: ${packet.payload.motion_type}`);
        return;
      }
      if (packet.event_type === "tool_pending") {
        appendMessage("system", `tool pending: ${packet.payload.tool_name}`);
        return;
      }
      if (packet.event_type === "tool_result") {
        appendMessage("system", `tool result: ${packet.payload.tool_name} -> ${packet.payload.result}`);
        return;
      }
      if (packet.event_type === "memory_recall") {
        appendMessage("system", `memory: ${JSON.stringify(packet.payload)}`);
        return;
      }
      if (packet.event_type === "system_status") {
        appendMessage("system", `status: ${JSON.stringify(packet.payload)}`);
      }
    }

    async function sendPrompt() {
      const text = promptEl.value.trim();
      if (!text) return;
      appendMessage("user", text);
      currentAssistantBubble = null;
      eventStatusEl.textContent = "sending...";
      promptEl.value = "";
      sendBtn.disabled = true;

      try {
        const response = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, session_id: sessionId }),
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split("\\n\\n");
          buffer = chunks.pop() || "";

          for (const chunk of chunks) {
            for (const line of chunk.split("\\n")) {
              if (!line.startsWith("data: ")) continue;
              const jsonText = line.slice(6);
              const packet = JSON.parse(jsonText);
              handlePacket(packet);
            }
          }
        }
      } catch (error) {
        appendMessage("system", `error: ${String(error)}`);
      } finally {
        sendBtn.disabled = false;
        refreshHealth();
      }
    }

    async function resetSession() {
      await fetch(`/sessions/${sessionId}/reset`, { method: "POST" });
      appendMessage("system", "session reset");
      currentAssistantBubble = null;
      refreshHealth();
    }

    sendBtn.addEventListener("click", sendPrompt);
    refreshBtn.addEventListener("click", refreshHealth);
    resetBtn.addEventListener("click", resetSession);
    promptEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendPrompt();
      }
    });

    refreshHealth();
    appendMessage("system", "ready");
  </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    html_path = Path(__file__).with_name("app_shell.html")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> JSONResponse:
    ollama_status = await _safe_ollama_health()
    active_profile = get_active_profile()
    return JSONResponse(
        {
            "status": "ok",
            "ollama": ollama_status,
            "active_model": active_profile,
            "character_profile": character_profile_stats(),
            "memory": memory_hub.stats(),
            "sessions": len(session_store.list_sessions()),
        }
    )


@app.get("/tools")
async def tools() -> JSONResponse:
    return JSONResponse({"tools": get_tool_catalog()})


@app.get("/models")
async def models() -> JSONResponse:
    profiles = list_model_profiles()
    installed_names: List[str] = []
    try:
        installed_names = await ollama_installed_models()
    except Exception:
        installed_names = []

    active_profile = get_active_profile()
    items = []
    for profile in profiles:
        item = dict(profile)
        item["installed"] = profile["model_name"] in installed_names
        item["active"] = profile["id"] == active_profile["id"]
        items.append(item)
    return JSONResponse({"models": items, "active_model_id": active_profile["id"]})


@app.post("/models/select")
async def select_model(request: ModelSelectRequest) -> JSONResponse:
    try:
        profile = set_active_profile(request.model_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="model profile not found")
    return JSONResponse({"status": "ok", "active_model": profile})


@app.get("/sessions")
async def sessions() -> JSONResponse:
    return JSONResponse({"sessions": [snapshot.model_dump(mode="json") for snapshot in session_store.list_sessions()]})


@app.get("/sessions/{session_id}")
async def session_detail(session_id: str) -> JSONResponse:
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return JSONResponse(
        {
            "session_id": session.session_id,
            "history": [message.model_dump(mode="json") for message in session.history],
            "completed_turns": list(session.completed_turns),
            "scene_state": dict(session.scene_state),
            "delta_summary": session.delta_summary,
            "drift_events": list(session.drift_events[-20:]),
        }
    )


@app.post("/sessions/{session_id}/reset")
async def reset_session(session_id: str) -> JSONResponse:
    session_store.reset(session_id)
    return JSONResponse({"status": "ok", "session_id": session_id})


@app.post("/history/clear")
async def clear_history() -> JSONResponse:
    session_store.clear_all()
    memory_hub.clear_all()
    return JSONResponse({"status": "ok"})


@app.get("/demo/ten-rally")
async def ten_rally_demo() -> JSONResponse:
    candidates = [
        DATA_DIR / "ten_rally_demo_ascii.json",
        DATA_DIR / "ten_rally_demo.json",
    ]
    for path in candidates:
        if path.exists():
            return JSONResponse({"turns": json.loads(path.read_text(encoding="utf-8")), "source": path.name})
    raise HTTPException(status_code=404, detail="demo log not found")


async def stream_chat_turn(session: ChatSession, user_text: str) -> AsyncGenerator[ControlPacket, None]:
    yield _packet("system_status", StatusPayload(status="queued", detail="Request received. Preparing response."))
    yield _packet("thinking_summary", "入力を受け取ったよ。まずは応答の準備をしているよ。")
    yield _packet("plan_summary", "モデルを呼び出して最初の返答を待っているよ。")

    recalled = memory_hub.recall(user_text) if _should_recall_memory(user_text) else []
    captured_facts = memory_hub.capture_user_facts(user_text)

    if recalled:
        yield _packet("memory_recall", {"items": recalled})
    if captured_facts:
        yield _packet("memory_recall", {"captured_facts": captured_facts})

    assistant_visible_text: List[str] = []
    try:
        messages = build_messages(
            user_text=user_text,
            chat_history=session.history,
            tool_definitions="(disabled in chat mode)",
            rag_memories=recalled,
            scene_state=session.scene_state,
            delta_summary=session.delta_summary,
        )
        try:
            async for chunk in _iter_with_timeout(generate_stream(messages), TURN_STREAM_TIMEOUT_SECONDS):
                assistant_visible_text.append(chunk)
        except asyncio.TimeoutError:
            detail = f"Model response exceeded {TURN_STREAM_TIMEOUT_SECONDS:.0f}s."
            yield _packet(
                "system_status",
                StatusPayload(
                    status="llm_timeout",
                    detail=detail,
                ),
            )
            failure_text = user_visible_llm_failure_message(detail)
            assistant_visible_text.append(failure_text)
    except LLMEngineError as exc:
        detail = str(exc)
        yield _packet("system_status", StatusPayload(status="llm_error", detail=detail))
        failure_text = user_visible_llm_failure_message(detail)
        assistant_visible_text.append(failure_text)

    assistant_text = strip_stage_directions(strip_residual_control_tags("".join(assistant_visible_text))).strip()
    assistant_text = normalize_yachiyo_output(assistant_text)
    previous_assistant = next((message.content for message in reversed(session.history) if message.role == "assistant"), "")
    drift_report = detect_drift(assistant_text, user_text=user_text, previous_reply=previous_assistant)
    if drift_report.drifted:
        session.drift_events.append({"user": user_text[:160], "reasons": ",".join(drift_report.reasons)})
        assistant_text = safe_recovery_reply(user_text)
    if (
        _is_repetitive_reply(assistant_text, previous_assistant)
        or _is_user_echo(assistant_text, user_text)
        or _looks_like_broken_dialogue(assistant_text)
    ):
        replacement = _build_nonrepetitive_reply(user_text)
        if replacement:
            assistant_text = replacement
    assistant_text = _strip_non_greeting_prefix(user_text, assistant_text)
    if _needs_troubleshooting_repair(user_text, assistant_text):
        assistant_text = _build_troubleshooting_reply(user_text)
    if _needs_casual_repair(user_text, assistant_text) or _needs_question_repair(user_text, assistant_text):
        assistant_text = _build_casual_reply(user_text, previous_assistant=previous_assistant)
    for chunk in _emit_text_chunks(assistant_text):
        yield _packet("text_chunk", chunk)
    session.history.append(ChatMessage(role="user", content=user_text))
    if assistant_text:
        session.history.append(ChatMessage(role="assistant", content=assistant_text))
        session.completed_turns.append({"user": user_text, "assistant": assistant_text})
        _update_session_state(session, user_text, assistant_text)
        episode_summary = memory_hub.summarize_recent_turns(session.completed_turns)
        if episode_summary:
            transcript = "\n".join(
                f"user: {turn['user']}\nassistant: {turn['assistant']}"
                for turn in session.completed_turns[-5:]
            )
            memory_hub.add_episode(episode_summary, transcript=transcript, turn_count=5)
    session_store.save()


def _update_session_state(session: ChatSession, user_text: str, assistant_text: str) -> None:
    mode = "troubleshooting" if _is_troubleshooting_text(user_text) else session.scene_state.get("mode", "normal")
    topic = _extract_topic(user_text) or session.scene_state.get("topic", "general chat")
    open_loop = _extract_open_loop(user_text, assistant_text)
    tone = "practical" if mode == "troubleshooting" else "casual"
    session.scene_state = {
        "mode": mode,
        "topic": topic,
        "user_goal": _truncate_state_value(user_text),
        "assistant_stance": "reply directly while preserving Yachiyo style",
        "open_loop": open_loop,
        "tone": tone,
    }
    session.delta_summary = _build_delta_summary(session.completed_turns[-4:], session.scene_state)


def _is_troubleshooting_text(text: str) -> bool:
    lowered = text.lower()
    return any(
        keyword in lowered
        for keyword in ("error", "fail", "failed", "bug")
    ) or any(keyword in text for keyword in ("できない", "反応", "送信", "押せない", "壊れ", "動かない", "エラー"))


def _extract_topic(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.strip())
    if not compact:
        return ""
    return _truncate_state_value(compact)


def _extract_open_loop(user_text: str, assistant_text: str) -> str:
    if _is_troubleshooting_text(user_text) and ("?" in assistant_text or "？" in assistant_text):
        return "assistant asked a follow-up question"
    if _is_troubleshooting_text(user_text):
        return "check whether the proposed fix resolved the issue"
    return "continue current topic"


def _build_delta_summary(turns: List[Dict[str, str]], scene_state: Dict[str, str]) -> str:
    if not turns:
        return "No prior turns."
    recent = turns[-3:]
    lines = [
        f"mode={scene_state.get('mode', 'normal')}",
        f"topic={scene_state.get('topic', 'general chat')}",
        f"open_loop={scene_state.get('open_loop', 'continue current topic')}",
    ]
    for turn in recent:
        user = _truncate_state_value(turn.get("user", ""))
        assistant = _truncate_state_value(turn.get("assistant", ""))
        lines.append(f"user: {user} / assistant: {assistant}")
    return "\n".join(lines)


def _truncate_state_value(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _should_recall_memory(user_text: str) -> bool:
    normalized = re.sub(r"\s+", "", user_text.lower())
    greeting_tokens = {
        "こんにちは",
        "こんばんは",
        "おはよう",
        "やあ",
        "うっす",
        "hello",
        "hi",
        "hey",
    }
    if normalized in greeting_tokens:
        return False
    return len(normalized) >= 6


def _normalize_for_repeat_check(text: str) -> str:
    return re.sub(r"[\s\u3000、。，．！？!?…\-ー]+", "", text.lower())


def _is_repetitive_reply(candidate: str, previous_assistant: str) -> bool:
    if not candidate or not previous_assistant:
        return False
    left = _normalize_for_repeat_check(candidate)
    right = _normalize_for_repeat_check(previous_assistant)
    if not left or not right:
        return False
    if left == right:
        return True
    if len(left) >= 12 and len(right) >= 12 and (left in right or right in left):
        return True
    return False


def _is_user_echo(candidate: str, user_text: str) -> bool:
    if not candidate or not user_text:
        return False
    left = _normalize_for_repeat_check(candidate)
    right = _normalize_for_repeat_check(user_text)
    if not left or not right:
        return False
    if left == right:
        return True
    shorter = min(len(left), len(right))
    if shorter >= 10 and (left in right or right in left):
        return True
    return False


def _looks_like_broken_dialogue(text: str) -> bool:
    if not text:
        return True
    lowered = text.lower()
    if lowered.count("...") >= 3 or lowered.count("…") >= 3:
        return True
    if text.count("ヤッチョ") >= 2:
        return True
    if re.search(r"(.{2,12}?)\1{2,}", text):
        return True
    return False


def _build_nonrepetitive_reply(user_text: str) -> str:
    text = user_text.strip()
    if not text:
        return ""
    opinion_subject = _extract_opinion_subject(text)
    if opinion_subject:
        return f"{opinion_subject}の話として受け取る。さっきの返しは捨てて、今の文脈から返す。"
    if len(text) <= 18:
        if _is_troubleshooting_text(text):
            return "入力か通信のどちらかで見直す。さっきと同じ返しにはしない。"
        topic = _short_topic_label(text)
        return f"{topic}として受け取る。さっきと同じ返しにはしない。"
    topic = _short_topic_label(text)
    return f"{topic}の話として受け取る。さっきの返しは捨てて、今の文脈から返す。"


def _is_greeting_text(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text.lower())
    return normalized in {"こんにちは", "こんばんは", "おはよう", "やあ", "うっす", "hello", "hi", "hey"}


def _strip_non_greeting_prefix(user_text: str, assistant_text: str) -> str:
    if _is_greeting_text(user_text):
        return assistant_text
    return re.sub(r"^ヤオヨロー[！!。]?\s*", "", assistant_text).strip()


def _needs_troubleshooting_repair(user_text: str, assistant_text: str) -> bool:
    if not _is_troubleshooting_text(user_text):
        return False
    lowered = assistant_text.lower()
    useful_markers = ("原因", "確認", "まず", "試", "押した", "通信", "ログ", "表示", "エラー")
    if any(marker in assistant_text for marker in useful_markers):
        return False
    if lowered.startswith("ヤオヨロー") or "どうしましたか" in assistant_text or "教えてくれないかな" in assistant_text:
        return True
    return True


def _build_troubleshooting_reply(user_text: str) -> str:
    if "スマホ" in user_text and "送信" in user_text:
        return "送信イベントか通信経路のどちらかで止まっていそう。まずは押した直後にステータス表示かネットワークリクエストが動くか見て。"
    if "時刻" in user_text:
        return "時刻そのものより、時刻取得を呼ぶ条件分岐が誤作動していそう。まずは時刻系キーワードで別処理に入っていないか見て。"
    return "原因候補は入力処理か通信処理のどちらかだね。まずは直前の操作と、画面に出ている表示を一つずつ確認しよう。"


def _needs_casual_repair(user_text: str, assistant_text: str) -> bool:
    if _is_troubleshooting_text(user_text) or _is_greeting_text(user_text):
        return False
    casual_markers = ("疲れた", "しんどい", "だるい", "眠い", "ひま", "なんか")
    if not any(marker in user_text for marker in casual_markers):
        return False
    if "？" in assistant_text or "?" in assistant_text:
        return True
    if assistant_text.startswith("ヤオヨロー"):
        return True
    return False


def _needs_question_repair(user_text: str, assistant_text: str) -> bool:
    if _is_troubleshooting_text(user_text) or _is_greeting_text(user_text):
        return False
    question_count = assistant_text.count("？") + assistant_text.count("?")
    if question_count >= 1 and assistant_text.rstrip().endswith(("？", "?")):
        return True
    if question_count >= 2:
        return True
    questiony_phrases = (
        "何かな",
        "どうした",
        "どういうこと",
        "何を指す",
        "何のこと",
        "どんな感じ",
        "教えて",
        "教えてくれ",
        "次回は",
        "どんな",
    )
    return any(phrase in assistant_text for phrase in questiony_phrases) and question_count >= 1


def _build_casual_reply(user_text: str, previous_assistant: str = "") -> str:
    if "疲れた" in user_text or "しんどい" in user_text:
        return _avoid_exact_repeat("それはしんどいね。今日は無理にがんばらず、だらっと話すくらいでいいよ、ヤチヨ的には。", previous_assistant)
    if "だるい" in user_text or "眠い" in user_text:
        return _avoid_exact_repeat("それはもう休み寄りでいこう。重い話は後回しでもいいよ、よしよし。", previous_assistant)
    if "ひま" in user_text:
        return _avoid_exact_repeat("じゃあ軽く話そう。思いついたことをそのまま投げてくれればいいよ、ヤッチョは聞くのです。", previous_assistant)
    if "についてどう思う" in user_text or "どう思う" in user_text:
        subject = _extract_opinion_subject(user_text)
        return _avoid_exact_repeat(_opinion_repair_reply(subject or "その話"), previous_assistant)
    if len(user_text.strip()) <= 18:
        topic = _short_topic_label(user_text)
        suffix = "" if topic.endswith("話") else "の話"
        return _avoid_exact_repeat(f"{topic}{suffix}でいこう。短くても、そこから普通に続けられる。", previous_assistant)
    topic = _short_topic_label(user_text)
    return _avoid_exact_repeat(_topic_repair_reply(topic), previous_assistant)


def _extract_opinion_subject(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.strip())
    compact = re.sub(r"[？?。！!]+$", "", compact)
    for suffix in ("についてどう思う", "をどう思う", "どう思う"):
        if suffix in compact:
            subject = compact.split(suffix, 1)[0].strip(" 　、。")
            return _short_topic_label(subject)
    return ""


def _short_topic_label(text: str, limit: int = 28) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip(" 　、。！？!?"))
    if not cleaned:
        return "その話"
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _opinion_repair_reply(subject: str) -> str:
    variants = [
        f"{subject}は、今の材料だけだと断定しにくいけど、まずは引っかかりのある題材だと思うよ。",
        f"{subject}は名前だけでも少し気になる。ヤチヨ的には、軽く掘る価値はありそう。",
        f"{subject}はまだ輪郭が薄いけど、話の中で育てるには悪くない題材だと思う。ちょっとキラキラしてるね。",
    ]
    return variants[_stable_variant(subject, len(variants))]


def _topic_repair_reply(topic: str) -> str:
    variants = [
        f"{topic}として受け取ったよ。大げさにせず、その流れで普通に話そう。",
        f"{topic}の方向でいこう。無理にまとめず、今の流れを優先するのです。",
        f"{topic}なら、そのまま続けられるね。変に質問攻めにはしないよ。",
    ]
    return variants[_stable_variant(topic, len(variants))]


def _stable_variant(text: str, size: int) -> int:
    if size <= 1:
        return 0
    return sum(ord(char) for char in text) % size


def _avoid_exact_repeat(candidate: str, previous_assistant: str) -> str:
    if not previous_assistant or not _is_repetitive_reply(candidate, previous_assistant):
        return candidate
    return "同じ返しになっていた。今の入力に合わせて、返答を組み直す。"


def _emit_text_chunks(text: str, size: int = 24) -> List[str]:
    if not text:
        return []
    return [text[index : index + size] for index in range(0, len(text), size)]


def _packet(event_type: str, payload: object) -> ControlPacket:
    return ControlPacket(event_type=event_type, payload=payload, timestamp=time.time())


def _collect_tool_requests(packet: ControlPacket) -> List[Tuple[str, Dict[str, str]]]:
    if packet.event_type != "tool_pending":
        return []
    payload = packet.payload if isinstance(packet.payload, dict) else {}
    tool_name = str(payload.get("tool_name", ""))
    args = payload.get("args", {})
    if not tool_name or not isinstance(args, dict):
        return []
    return [(tool_name, {str(key): str(value) for key, value in args.items()})]


async def _execute_tool_requests(
    tool_requests: List[Tuple[str, Dict[str, str]]],
    ) -> AsyncGenerator[Tuple[ControlPacket, Optional[ChatMessage]], None]:
    for tool_name, args in tool_requests:
        async for packet, tool_message in _run_tool(tool_name, args):
            yield packet, tool_message


async def _run_tool(
    tool_name: str,
    args: Dict[str, str],
) -> AsyncGenerator[Tuple[ControlPacket, Optional[ChatMessage]], None]:
    tool = get_tool(tool_name)
    if tool is None:
        yield _packet(
            "tool_result",
            ToolResultPayload(tool_name=tool_name, ok=False, result="Unknown tool requested."),
        ), None
        return

    if tool_name in DESTRUCTIVE_TOOLS:
        approval_packet = _packet(
            "tool_approval_req",
            ToolApprovalPayload(
                tool_name=tool_name,
                args=args,
                reason="This tool can change local files.",
            ),
        )
        yield approval_packet, None
        approved = await request_approval(tool_name, args)
        if not approved:
            result_packet = _packet(
                "tool_result",
                ToolResultPayload(
                    tool_name=tool_name,
                    ok=False,
                    result="User rejected the tool execution.",
                ),
            )
            yield result_packet, ChatMessage(role="tool", content=f"{tool_name}: User rejected the tool execution.")
            return

    handler = tool["handler"]
    try:
        result = handler(**args)
        if hasattr(result, "__await__"):
            result = await result
        result_packet = _packet(
            "tool_result",
            ToolResultPayload(tool_name=tool_name, ok=True, result=str(result)),
        )
        yield result_packet, ChatMessage(role="tool", content=f"{tool_name}: {result}")
    except Exception as exc:  # noqa: BLE001
        result_packet = _packet(
            "tool_result",
            ToolResultPayload(tool_name=tool_name, ok=False, result=str(exc)),
        )
        yield result_packet, ChatMessage(role="tool", content=f"{tool_name}: {exc}")


async def _safe_ollama_health() -> Dict[str, str]:
    try:
        return await ollama_healthcheck()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": str(exc)}


@app.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    session = session_store.get_or_create(request.session_id)

    async def event_stream():
        async for packet in stream_chat_turn(session, request.text):
            serialized = json.dumps(packet.model_dump(mode="json"), ensure_ascii=False)
            yield f"data: {serialized}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/chat/complete")
async def chat_complete(request: ChatRequest) -> JSONResponse:
    session = session_store.get_or_create(request.session_id)
    packets = []
    async for packet in stream_chat_turn(session, request.text):
        packets.append(packet.model_dump(mode="json"))
    return JSONResponse({"packets": packets, "session_id": session.session_id})


@app.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    session = session_store.get_or_create(None)
    await websocket.send_json(_packet("system_status", StatusPayload(status="connected", detail=session.session_id)).model_dump(mode="json"))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                request = ChatRequest.model_validate(json.loads(raw))
            except Exception as exc:  # noqa: BLE001
                await websocket.send_json(
                    _packet(
                        "system_status",
                        StatusPayload(status="bad_request", detail=str(exc)),
                    ).model_dump(mode="json")
                )
                continue

            if request.session_id:
                session = session_store.get_or_create(request.session_id)

            async for packet in stream_chat_turn(session, request.text):
                await websocket.send_json(packet.model_dump(mode="json"))
    except WebSocketDisconnect:
        return


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=False)
