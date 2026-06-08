# Yachiyo Roleplay System Revision Plan

Date: 2026-06-08

## Scope

This plan implements the local-LLM roleplay stabilization work described in the two PDF reports and the TechnoEdge reference about StreamingLLM and RoleLLM.

The current runtime model candidates are exactly:

- `gemma3:1b`
- `qwen3:1.7b`
- `qwen3:4b-instruct-2507-q4_K_M`

Operational default:

- `qwen3:1.7b`

Removed models are not part of the current plan:

- `qwen2.5:3b-instruct`
- `gemma4:e2b`
- `yuiseki/tinyswallow:1.5b`
- `hf.co/tensorblock/sarashina2.2-1b-instruct-v0.1-GGUF:Q2_K`
- `qwen3-vl:8b`

## Diagnosis

The unstable roleplay behavior is not mainly caused by too little character setting. The main risks are:

- Overloaded prompts that mix persona, lore, history, state, and instructions.
- Model-specific template mismatch, especially system-role handling and Qwen3 thinking behavior.
- Lack of explicit scene state and delta summary.
- Lore being injected too broadly.
- Late string cleanup instead of drift detection and one recovery attempt.
- No repeatable multi-turn evaluation harness.

## Architecture

The prompt must be built from explicit layers:

- Model adapter instruction.
- Stable short persona anchor.
- Small style examples.
- Scene state.
- Delta summary.
- Selective lore.
- Relevant memory.
- Recent turns.
- Post-history instruction.

Long conversations should retain a stable anchor near the start and move volatile details into compact state and summary fields. This follows the StreamingLLM attention-sink implication: keep stable control text near the front, do not rewrite it every turn.

RoleLLM/RoleBench implications:

- Extract role-specific QA and style examples from Yachiyo material.
- Evaluate with multi-turn roleplay probes, not only casual manual chat.
- Use data for prompt retrieval and evaluation before considering fine-tuning.

## Implementation Phases

### Phase 0: Prompt Inspection

Implement `scripts/inspect_prompt.py`.

Acceptance:

- Prints active model, adapter name, message roles, prompt char budget, persona/lore/state section lengths, and messages sent to Ollama.
- Confirms the persona anchor remains present.

### Phase 1: Model Adapter Layer

Implement `agent/model_adapters.py`.

Current adapters:

- `gemma3:1b`: compact, user-anchor preferred, stronger repeat penalty.
- `qwen3:1.7b`: Qwen3 no-thinking roleplay candidate.
- `qwen3:4b-instruct-2507-q4_K_M`: Qwen3 quality comparison candidate.

Acceptance:

- `llm_engine.py` no longer hardcodes all model-specific options.
- `prompt_builder.py` asks the adapter how to arrange system/user anchor behavior.

### Phase 2: Prompt Layering

Create:

- `yachiyo_spirit/persona_anchor.md`
- `yachiyo_spirit/style_examples.jsonl`
- `yachiyo_spirit/lorebook.jsonl`
- `yachiyo_spirit/role_questions.jsonl`

Acceptance:

- The old full profile is not dumped into every turn.
- Prompt inspection shows persona, lore, memory, state, and recent turns as separate layers.

### Phase 3: Scene State And Delta Summary

Extend session persistence with:

- `scene_state`
- `delta_summary`
- `drift_events`

Acceptance:

- `data/sessions.json` persists these fields.
- A 20-turn conversation can keep topic, user goal, and open loop without raw full-history dependence.

### Phase 4: Selective Lore Retrieval

Implement keyword-based lore selection from `lorebook.jsonl`.

Acceptance:

- Only 1-2 relevant lore entries are injected.
- Deep/caution lore is not injected into normal troubleshooting unless triggered.

### Phase 5: Drift Detection And Recovery

Implement `agent/drift_detector.py`.

Detect:

- User echo.
- Repetition.
- English stage directions.
- Generic assistant tone.
- Writing the user's actions or inner thoughts.
- Forbidden Yachiyo patterns.

Acceptance:

- A drift event is recorded.
- The app makes one recovery attempt when useful.
- If recovery fails, it returns a short safe response rather than broken output.

### Phase 6: Multi-turn Evaluation

Create:

- `evals/yachiyo_short_style.jsonl`
- `evals/yachiyo_medium_dialogues.jsonl`
- `evals/yachiyo_rolebench_mini.jsonl`
- `scripts/run_roleplay_eval.py`

Acceptance:

- Eval can run against the current app without changing production code.
- Reports latency, role adherence heuristics, user echo, repetition, forbidden phrase hits, and empty responses.

### Phase 7: Model Comparison

Current matrix:

- Speed baseline: `gemma3:1b`
- Default candidate: `qwen3:1.7b`
- Quality candidate: `qwen3:4b-instruct-2507-q4_K_M`

Acceptance:

- Model choice can be based on eval logs and latency, not only manual feel.

## Success Criteria

- 12-turn conversation has zero plain user echo.
- 12-turn conversation has zero English stage directions.
- 12-turn conversation has zero user-action or user-inner-thought writing.
- Troubleshooting answers include at least one concrete cause or next check.
- Normal chat does not inject heavy myth/fate/loneliness lore without a trigger.
- Prompt inspection shows stable persona anchor and separated scene/lore/history layers.
- `/health` is OK and `/models` lists only the three current candidates.
