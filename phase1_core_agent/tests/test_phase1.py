from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from agent import llm_engine
from agent.memory_hub import MemoryHub
from agent.prompt_builder import build_messages
from agent.stream_parser import StreamParser, strip_stage_directions
from config import OLLAMA_FIRST_TOKEN_TIMEOUT_SECONDS, TURN_STREAM_TIMEOUT_SECONDS
from main import SessionStore
from tools import pc_control


class StreamParserTests(unittest.TestCase):
    def test_parser_splits_text_and_control_packets(self) -> None:
        parser = StreamParser()
        packets = parser.feed("<thinking>plan it</thinking>Hello")
        packets.extend(parser.feed('<emotion intensity="0.5">smile</emotion><motion>nod</motion>'))
        event_types = [packet.event_type for packet in packets]
        self.assertEqual(
            event_types,
            ["thinking_summary", "text_chunk", "emotion_trigger", "motion_trigger"],
        )

    def test_parser_strips_residual_control_tags_from_text(self) -> None:
        parser = StreamParser()
        packets = parser.feed("Hello </emotion> world")
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].event_type, "text_chunk")
        self.assertEqual(packets[0].payload, "Hello world")

    def test_parser_strips_english_stage_directions(self) -> None:
        text = "(A slight, almost wistful sigh, a flicker of amusement in the eyes)\n\nヤチヨ、怖くない返事をするよ。"
        self.assertEqual(strip_stage_directions(text), "ヤチヨ、怖くない返事をするよ。")


class FallbackConversationTests(unittest.TestCase):
    def test_fallback_greeting_is_not_fixed_echo(self) -> None:
        async def gather() -> str:
            chunks = []
            async for chunk in llm_engine._generate_fallback(
                [{"role": "user", "content": "こんにちは。短く自己紹介して。"}]
            ):
                chunks.append(chunk)
            return "".join(chunks)

        result = asyncio.run(gather())
        self.assertIn("通常のAIアシスタント", result)
        self.assertNotIn("ヤチヨ", result)
        self.assertNotIn("Phase 1 の開発フォールバックで応答しているよ", result)

    def test_first_token_timeout_config_is_enabled(self) -> None:
        self.assertGreaterEqual(OLLAMA_FIRST_TOKEN_TIMEOUT_SECONDS, 1.0)

    def test_turn_stream_timeout_config_is_enabled(self) -> None:
        self.assertGreaterEqual(TURN_STREAM_TIMEOUT_SECONDS, 5.0)

    def test_plain_fallback_handles_casual_topics(self) -> None:
        async def gather(text: str) -> str:
            chunks = []
            async for chunk in llm_engine._generate_fallback([{"role": "user", "content": text}]):
                chunks.append(chunk)
            return "".join(chunks)

        picnic = asyncio.run(gather("今度ピクニックいくんだー"))
        self.assertTrue(picnic.strip())
        self.assertNotIn("ヤチヨ", picnic)

        phone = asyncio.run(gather("スマホ壊れちゃった"))
        self.assertTrue(phone.strip())
        self.assertNotIn("ヤチヨ", phone)

    def test_short_casual_topics_are_not_intercepted_before_model(self) -> None:
        reply = llm_engine._yachiyo_short_reply([{"role": "user", "content": "うんちしたい"}])
        self.assertIsNone(reply)

        reply = llm_engine._yachiyo_short_reply([{"role": "user", "content": "スマホ壊れちゃった"}])
        self.assertIsNone(reply)


    def test_generate_stream_uses_model_for_normal_short_chat(self) -> None:
        async def fake_ollama(_messages):
            yield "こんにちは。今日はちゃんと会話の流れに合わせて話すよ。"

        async def gather() -> str:
            chunks = []
            with patch.object(llm_engine, "_generate_from_ollama", fake_ollama):
                async for chunk in llm_engine.generate_stream([{"role": "user", "content": "こんにちは"}]):
                    chunks.append(chunk)
            return "".join(chunks)

        result = asyncio.run(gather())
        self.assertEqual(result, "こんにちは。今日はちゃんと会話の流れに合わせて話すよ。")

    def test_ollama_failure_does_not_use_canned_fallback(self) -> None:
        async def broken_ollama(_messages):
            raise RuntimeError("forced failure")
            yield ""  # pragma: no cover

        async def gather() -> str:
            chunks = []
            with patch.object(llm_engine, "_generate_from_ollama", broken_ollama):
                with self.assertRaises(llm_engine.LLMEngineError):
                    async for chunk in llm_engine.generate_stream([{"role": "user", "content": "うっす"}]):
                        chunks.append(chunk)
            return "".join(chunks)

        result = asyncio.run(gather())
        self.assertEqual(result, "")


class MemoryHubTests(unittest.TestCase):
    def test_memory_hub_captures_facts_and_recalls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            hub = MemoryHub(Path(temp_dir) / "memory.sqlite3")
            facts = hub.capture_user_facts("私はカレーが好きです")
            self.assertTrue(facts)
            recalled = hub.recall("カレー")
            self.assertTrue(any("カレー" in item for item in recalled))


class PromptBuilderTests(unittest.TestCase):
    def test_system_prompt_uses_plain_assistant_mode(self) -> None:
        messages = build_messages(
            user_text="こんにちは",
            chat_history=[],
            tool_definitions="(none)",
            rag_memories=[],
        )
        system_prompt = messages[0]["content"]
        self.assertIn("通常のAIアシスタント", system_prompt)
        self.assertIn("キャラクター、ロールプレイ、演技", system_prompt)
        self.assertIn("固有キャラクター設定を使わない", system_prompt)
        self.assertNotIn("Character profile:", system_prompt)
        self.assertNotIn("月見ヤチヨ Features", system_prompt)
        self.assertNotIn("ツクヨミの管理人", system_prompt)


class FileToolTests(unittest.TestCase):
    def test_file_tools_respect_temp_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_roots = pc_control.ALLOWED_FILE_ROOTS
            try:
                pc_control.ALLOWED_FILE_ROOTS = [Path(temp_dir).resolve()]
                message = pc_control.write_text_file("notes.txt", "hello")
                self.assertIn("Wrote", message)
                self.assertEqual(pc_control.read_text_file("notes.txt"), "hello")
                listing = pc_control.list_directory(".")
                self.assertIn("notes.txt", listing)
                deleted = pc_control.delete_file("notes.txt")
                self.assertIn("Deleted", deleted)
            finally:
                pc_control.ALLOWED_FILE_ROOTS = original_roots


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        memory_file = Path(self.temp_dir.name) / "memory.sqlite3"
        main.memory_hub = MemoryHub(memory_file)
        main.session_store = SessionStore()

        import agent.llm_engine as llm_engine

        self._original_enable_ollama = llm_engine.ENABLE_OLLAMA
        self._original_enable_dev_fallback = llm_engine.ENABLE_DEV_FALLBACK
        llm_engine.ENABLE_OLLAMA = False
        llm_engine.ENABLE_DEV_FALLBACK = True
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

        import agent.llm_engine as llm_engine

        llm_engine.ENABLE_OLLAMA = self._original_enable_ollama
        llm_engine.ENABLE_DEV_FALLBACK = self._original_enable_dev_fallback

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("memory", body)
        self.assertTrue(body["character_profile"]["loaded"])

    def test_root_page_exists(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("LLM Chat", response.text)
        self.assertIn("/ws/chat", response.text)
        self.assertNotIn("Yachiyo Chat", response.text)
        self.assertIn("メッセージを送信", response.text)
        self.assertIn("loadCurrentHistory()", response.text)
        self.assertNotIn("sessions[sessions.length - 1]", response.text)
        self.assertIn("/models/select", response.text)
        self.assertIn("/chat/complete", response.text)

    def test_chat_endpoint_streams_tool_loop(self) -> None:
        response = self.client.post("/chat", json={"text": "time please", "session_id": "test-session"})
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('"status": "queued"', body)
        self.assertIn('"event_type": "tool_pending"', body)
        self.assertIn('"event_type": "tool_result"', body)
        self.assertIn("get_current_time", body)

    def test_chat_complete_endpoint_returns_packets(self) -> None:
        response = self.client.post("/chat/complete", json={"text": "time please", "session_id": "complete-session"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["session_id"], "complete-session")
        event_types = [packet["event_type"] for packet in body["packets"]]
        self.assertIn("system_status", event_types)
        self.assertIn("tool_pending", event_types)
        self.assertIn("tool_result", event_types)

    def test_sessions_endpoint_reports_active_session(self) -> None:
        self.client.post("/chat", json={"text": "hello", "session_id": "alpha"})
        response = self.client.get("/sessions")
        self.assertEqual(response.status_code, 200)
        sessions = response.json()["sessions"]
        self.assertTrue(any(session["session_id"] == "alpha" for session in sessions))

    def test_models_endpoint_returns_profiles(self) -> None:
        response = self.client.get("/models")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["models"])
        self.assertIn("active_model_id", body)

    def test_model_select_endpoint_switches_profile(self) -> None:
        response = self.client.post("/models/select", json={"model_id": "qwen25_3b"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["active_model"]["id"], "qwen25_3b")

    def test_session_detail_endpoint_returns_history(self) -> None:
        self.client.post("/chat", json={"text": "hello", "session_id": "alpha"})
        response = self.client.get("/sessions/alpha")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["session_id"], "alpha")
        self.assertTrue(any(message["role"] == "user" for message in body["history"]))

    def test_websocket_round_trip(self) -> None:
        with self.client.websocket_connect("/ws/chat") as websocket:
            first_message = websocket.receive_json()
            self.assertEqual(first_message["event_type"], "system_status")
            websocket.send_text(json.dumps({"text": "time please"}))
            event_types = []
            for _ in range(8):
                message = websocket.receive_json()
                event_types.append(message["event_type"])
                if message["event_type"] == "text_chunk":
                    break
            self.assertIn("tool_pending", event_types)
            self.assertIn("tool_result", event_types)


if __name__ == "__main__":
    unittest.main()
