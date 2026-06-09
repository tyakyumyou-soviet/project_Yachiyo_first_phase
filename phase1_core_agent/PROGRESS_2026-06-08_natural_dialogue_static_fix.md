# Natural Dialogue Static Fix - 2026-06-08

## Problem

Yachiyo roleplay was failing as ordinary conversation because several runtime control files contained mojibake strings. The broken strings affected:

- system prompt contracts
- runtime mode hints
- fallback replies
- drift recovery replies
- tests and UI labels
- persisted local session history

This made the model receive unclear instructions and made previous bad replies likely to be replayed through history.

## Changes

- Rebuilt `agent/prompt_builder.py` with clear Japanese instructions:
  - ordinary conversation first
  - Yachiyo flavor only as a light layer
  - no repeated questions in casual chat
  - no tool names or stage directions
- Rebuilt `agent/llm_engine.py` fallback and output normalization with clear Japanese.
- Rebuilt `agent/drift_detector.py` recovery text with clear Japanese.
- Rebuilt `agent/persona.py` so the legacy prompt template no longer contains mojibake.
- Rebuilt `tests/test_phase1.py` with meaningful Japanese assertions.
- Cleared `data/sessions.json` to remove bad persisted conversation examples.
- Cleaned browser UI labels in `app_shell.html`.
- Updated README notes so chat mode no longer claims fallback tool loops are part of normal behavior.
- Added general question-heavy reply repair and stopped normal chat from storing `assistant asked a follow-up question` as persistent state.
- Expanded the question-heavy repair to catch unknown-term prompts such as `何のこと？` and convert `どう思う` prompts into non-question casual replies.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1
```

Result: 26 tests passed.

```powershell
.\.venv\Scripts\python.exe .\scripts\inspect_prompt.py "FUSHIについてどう思う" --json
```

Result: prompt output used clean Japanese instructions and included the rule `雑談では質問で終わらせない`.

```powershell
.\.venv\Scripts\python.exe -c "... POST /chat/complete ..."
```

Result after server restart: `FUSHIについてどう思う` returned a non-question reply:

`まだ材料は少ないけど、まずは普通に面白そうだと思う。変に決めつけず、話の中で輪郭を見ていけばいい。`

The live history and memory store were cleared after verification:

- `semantic_count=0`
- `episode_count=0`
- `sessions=0`
