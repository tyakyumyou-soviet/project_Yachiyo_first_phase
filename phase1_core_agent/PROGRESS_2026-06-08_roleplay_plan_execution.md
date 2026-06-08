# 2026-06-08 Roleplay Plan Execution

## Implemented

- Rewrote `YACHIYO_ROLEPLAY_SYSTEM_REVISION_PLAN_2026-06-08.md` so the current model plan is exactly:
  - `gemma3:1b`
  - `qwen3:1.7b`
  - `qwen3:4b-instruct-2507-q4_K_M`
- Added `agent/model_adapters.py`.
- Added `agent/drift_detector.py`.
- Rebuilt `agent/prompt_builder.py` around separate prompt layers:
  - model adapter
  - persona anchor
  - style examples
  - scene state
  - delta summary
  - selective lore
  - relevant memory
  - runtime mode
  - tools
  - final turn instruction
- Rebuilt `agent/llm_engine.py` so model-specific options and message adaptation go through the adapter layer.
- Extended `ChatSession` with:
  - `scene_state`
  - `delta_summary`
  - `drift_events`
- Persisted the new session fields in `SessionStore`.
- Added drift detection and one recovery attempt before storing an assistant reply.
- Added roleplay source data:
  - `yachiyo_spirit/persona_anchor.md`
  - `yachiyo_spirit/style_examples.jsonl`
  - `yachiyo_spirit/lorebook.jsonl`
  - `yachiyo_spirit/role_questions.jsonl`
- Added eval data:
  - `evals/yachiyo_short_style.jsonl`
  - `evals/yachiyo_medium_dialogues.jsonl`
  - `evals/yachiyo_rolebench_mini.jsonl`
- Added scripts:
  - `scripts/inspect_prompt.py`
  - `scripts/run_roleplay_eval.py`

## Verification

- `.venv\Scripts\python.exe -m unittest tests.test_phase1` passed: 16 tests.
- `.venv\Scripts\python.exe scripts\inspect_prompt.py "スマホで送信できない" --json` succeeded.
- `.venv\Scripts\python.exe scripts\run_roleplay_eval.py --max-cases 1` succeeded.
- After adding coverage for the new features, `.venv\Scripts\python.exe -m unittest tests.test_phase1` passed: 19 tests.
- Persistent server start was completed with `C:\tmp\start_yachiyo.ps1`.
- `GET http://127.0.0.1:8000/health` returned `status: ok` with active model `qwen3:1.7b`.
- `GET http://127.0.0.1:8000/models` returned exactly `gemma3:1b`, `qwen3:1.7b`, and `qwen3:4b-instruct-2507-q4_K_M`.
- `POST http://100.114.99.4:8000/chat` streamed a greeting response starting with `ヤオヨロー！`.
- Browser verification at `http://100.114.99.4:8000/` showed `ready` status and exactly the three current model options.

## Notes

- The first evaluation run used a greeting case and passed through the deterministic short-reply path.
- Longer live model evaluation can now be run against the active server.
- Manual fallback start command: `powershell -NoProfile -ExecutionPolicy Bypass -File C:\tmp\start_yachiyo.ps1`.
