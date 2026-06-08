from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent import llm_engine
from agent.drift_detector import detect_drift
from agent.memory_hub import MemoryHub
from agent.model_adapters import get_model_adapter
from agent.prompt_builder import build_messages, inspect_prompt
from agent.stream_parser import StreamParser, strip_stage_directions
from main import SessionStore
from model_manager import MODEL_STATE_PATH
from schemas import ChatMessage
from tools import pc_control


class StreamParserTests(unittest.TestCase):
    def test_parser_splits_text_and_control_packets(self) -> None:
        parser = StreamParser()
        packets = parser.feed("<thinking>plan it</thinking>Hello")
        packets.extend(parser.feed('<emotion intensity="0.5">smile</emotion><motion>nod</motion>'))
        self.assertEqual(
            [packet.event_type for packet in packets],
            ["thinking_summary", "text_chunk", "emotion_trigger", "motion_trigger"],
        )

    def test_parser_strips_english_stage_directions(self) -> None:
        self.assertEqual(strip_stage_directions("(A slight sigh)\n\nこんにちは"), "こんにちは")


class FallbackConversationTests(unittest.TestCase):
    def test_fallback_greeting_is_plain_and_no_tool_tag(self) -> None:
        async def gather() -> str:
            chunks = []
            async for chunk in llm_engine._generate_fallback([{"role": "user", "content": "こんにちは"}]):
                chunks.append(chunk)
            return "".join(chunks)

        result = asyncio.run(gather())
        self.assertIn("ヤオヨロー！", result)
        self.assertNotIn("Phase 1", result)
        self.assertNotIn("get_current_time", result)
        self.assertNotIn("<tool", result)

    def test_output_normalizer_removes_kashira_ara_and_tool_tags(self) -> None:
        normalized = llm_engine.normalize_yachiyo_output("あら、そうかしら <tool name=\"get_current_time\"></tool>")
        self.assertEqual(normalized, "そうかな")


class MemoryHubTests(unittest.TestCase):
    def test_memory_hub_captures_facts_and_recalls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            hub = MemoryHub(Path(temp_dir) / "memory.sqlite3")
            hub.add_semantic_memory("好きな食べ物はカレーです")
            recalled = hub.recall("カレー")
            self.assertTrue(any("カレー" in item for item in recalled))


class SessionStorePersistenceTests(unittest.TestCase):
    def test_session_store_persists_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "sessions.json"
            store = SessionStore(store_path)
            session = store.get_or_create("persisted")
            session.history.append(ChatMessage(role="user", content="こんにちは"))
            session.history.append(ChatMessage(role="assistant", content="ヤオヨロー！今日はどうする？"))
            session.completed_turns.append({"user": "こんにちは", "assistant": "ヤオヨロー！今日はどうする？"})
            session.scene_state = {"mode": "normal", "topic": "greeting"}
            session.delta_summary = "topic=greeting"
            session.drift_events.append({"user": "echo", "reasons": "user_echo"})
            store.save()

            restored = SessionStore(store_path)
            loaded = restored.get("persisted")
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(len(loaded.history), 2)
            self.assertEqual(loaded.history[1].content, "ヤオヨロー！今日はどうする？")
            self.assertEqual(loaded.scene_state["topic"], "greeting")
            self.assertEqual(loaded.delta_summary, "topic=greeting")
            self.assertEqual(loaded.drift_events[0]["reasons"], "user_echo")

    def test_session_store_can_clear_all(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "sessions.json"
            store = SessionStore(store_path)
            store.get_or_create("a")
            store.get_or_create("b")
            self.assertEqual(len(store.list_sessions()), 2)
            store.clear_all()
            self.assertEqual(len(store.list_sessions()), 0)

    def test_short_greeting_does_not_trigger_memory_recall(self) -> None:
        self.assertFalse(main._should_recall_memory("こんにちは"))
        self.assertFalse(main._should_recall_memory("hi"))
        self.assertTrue(main._should_recall_memory("昨日の続きなんだけど"))

    def test_repetition_guard_detects_same_reply(self) -> None:
        self.assertTrue(main._is_repetitive_reply("今日はその話を続けよう。", "今日はその話を続けよう。"))
        self.assertFalse(main._is_repetitive_reply("別の観点から見ると原因候補は二つある。", "今日はその話を続けよう。"))

    def test_user_echo_guard_detects_plain_echo(self) -> None:
        self.assertTrue(main._is_user_echo("スマホから送信できない", "スマホから送信できない"))
        self.assertTrue(main._is_user_echo("スマホから送信できない。", "スマホから送信できない"))
        self.assertFalse(main._is_user_echo("送信失敗なら通信経路を先に見る。", "スマホから送信できない"))

    def test_nonrepetitive_reply_does_not_echo_user_text(self) -> None:
        reply = main._build_nonrepetitive_reply("スマホで押せない")
        self.assertNotIn("スマホで押せない", reply)
        self.assertTrue(reply)

    def test_troubleshooting_repair_produces_direct_reply(self) -> None:
        self.assertTrue(main._needs_troubleshooting_repair("スマホで送信できない", "ヤオヨロー！どうした？"))
        repaired = main._build_troubleshooting_reply("スマホで送信できない")
        self.assertIn("送信イベント", repaired)
        self.assertIn("ネットワークリクエスト", repaired)

    def test_non_greeting_reply_strips_yaoyoroo_prefix(self) -> None:
        stripped = main._strip_non_greeting_prefix("なんか疲れた", "ヤオヨロー！今日はしんどそうだな。")
        self.assertFalse(stripped.startswith("ヤオヨロー"))

    def test_casual_repair_softens_question_heavy_reply(self) -> None:
        self.assertTrue(main._needs_casual_repair("なんか疲れた", "何がつらいの？"))
        repaired = main._build_casual_reply("なんか疲れた")
        self.assertIn("無理にがんばらず", repaired)

    def test_broken_dialogue_guard_detects_repeated_name(self) -> None:
        self.assertTrue(main._looks_like_broken_dialogue("ヤッチョヤッチョヤッチョ"))
        self.assertTrue(main._looks_like_broken_dialogue("........"))
        self.assertFalse(main._looks_like_broken_dialogue("送信ボタンが反応しないならイベント経路を見る。"))


class PromptBuilderTests(unittest.TestCase):
    def test_system_prompt_uses_single_history_channel(self) -> None:
        messages = build_messages(
            user_text="こんにちは",
            chat_history=[ChatMessage(role="assistant", content="了解")],
            tool_definitions="(none)",
            rag_memories=[],
        )
        system_prompt = messages[0]["content"]
        self.assertIn("最新のユーザー入力にだけ答える", system_prompt)
        self.assertIn("挨拶入力以外では「ヤオヨロー！」から始めない", system_prompt)
        self.assertNotIn("Available Tools", system_prompt)
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[-1]["role"], "user")

    def test_character_profile_is_condensed(self) -> None:
        messages = build_messages(
            user_text="相談したい",
            chat_history=[],
            tool_definitions="(none)",
            rag_memories=[],
        )
        self.assertLess(len(messages[0]["content"]), 2200)

    def test_troubleshooting_mode_hint_is_added_for_bug_reports(self) -> None:
        messages = build_messages(
            user_text="送信するとエラーになる",
            chat_history=[ChatMessage(role="user", content="スマホから送信できない")],
            tool_definitions="(none)",
            rag_memories=[],
        )
        system_prompt = messages[0]["content"]
        self.assertIn("不具合相談として扱う", system_prompt)
        self.assertIn("次に確認することを一つだけ示す", system_prompt)

    def test_prompt_inspection_reports_layers_and_adapter(self) -> None:
        messages, inspection = inspect_prompt(
            user_text="スマホで送信できない",
            chat_history=[],
            tool_definitions="(none)",
            rag_memories=[],
            scene_state={"mode": "troubleshooting", "topic": "send failure"},
            delta_summary="send failure investigation",
        )
        self.assertTrue(messages)
        self.assertIn("persona_anchor", inspection.sections)
        self.assertIn("lore", inspection.sections)
        self.assertTrue(inspection.adapter_name)

    def test_qwen3_adapter_uses_no_think_prefix(self) -> None:
        adapter = get_model_adapter("qwen3:1.7b")
        self.assertTrue(adapter.supports_thinking_toggle)
        self.assertIn("/no_think", adapter.roleplay_prefix)


class DriftDetectorTests(unittest.TestCase):
    def test_detects_user_echo_and_stage_direction(self) -> None:
        echo = detect_drift("スマホで送信できない", user_text="スマホで送信できない")
        self.assertIn("user_echo", echo.reasons)
        stage = detect_drift("(A slight smile) こんにちは", user_text="こんにちは")
        self.assertIn("english_stage_direction", stage.reasons)


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
        main.session_store = SessionStore(Path(self.temp_dir.name) / "sessions.json")
        self._original_model_state = MODEL_STATE_PATH.read_text(encoding="utf-8") if MODEL_STATE_PATH.exists() else None
        self._original_enable_ollama = llm_engine.ENABLE_OLLAMA
        self._original_enable_dev_fallback = llm_engine.ENABLE_DEV_FALLBACK
        llm_engine.ENABLE_OLLAMA = False
        llm_engine.ENABLE_DEV_FALLBACK = True
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        if self._original_model_state is None:
            try:
                MODEL_STATE_PATH.unlink()
            except FileNotFoundError:
                pass
        else:
            MODEL_STATE_PATH.write_text(self._original_model_state, encoding="utf-8")
        llm_engine.ENABLE_OLLAMA = self._original_enable_ollama
        llm_engine.ENABLE_DEV_FALLBACK = self._original_enable_dev_fallback

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("memory", body)
        self.assertTrue(body["character_profile"]["loaded"])

    def test_clear_history_endpoint(self) -> None:
        session = main.session_store.get_or_create("wipe-me")
        session.history.append(ChatMessage(role="user", content="こんにちは"))
        session.history.append(ChatMessage(role="assistant", content="ヤオヨロー！今日はどうする？"))
        main.session_store.save()
        main.memory_hub.add_semantic_memory("好きな食べ物はカレーです")
        response = self.client.post("/history/clear")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(main.session_store.list_sessions(), [])
        self.assertEqual(main.memory_hub.stats()["semantic_count"], 0)


if __name__ == "__main__":
    unittest.main()
