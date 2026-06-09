# Repeat Fix - 2026-06-09

## Problem

The chat could collapse into repeated safe replies. The main causes were:

- repair handlers returned fixed generic text too often
- the user-echo repair compared candidate replies against the current user text as if it were the previous assistant reply
- Gemma user-anchor prompts could leak into the deterministic fallback path as the apparent user message
- episodic memory summaries were saved on every turn after the interval and could keep re-injecting similar topics
- `memory_hub.py` still contained mojibake in fact-capture patterns

## Changes

- Made casual repair and non-repetition repair topic-aware.
- Added stable per-topic reply variants so different topics do not receive the same repair sentence.
- Fixed Gemma fallback extraction so only text after `User message:` or `最新のユーザー入力:` is treated as user input.
- Rebuilt `agent/memory_hub.py` with clean Japanese fact-capture patterns.
- Blocked generic repair text from being stored as memory.
- Limited episodic summaries to exact interval boundaries and deduplicated topics.
- Added regression tests for fallback extraction, memory filtering, interval-limited episode summaries, and topic-varying repair replies.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1
```

Result: 32 tests passed.

In-process API check with fallback enabled produced different replies:

- `FUSHIについてどう思う` -> `FUSHIは話の中で輪郭が出てきそうな感じがある。`
- `お茶漬けについてどう思う` -> `お茶漬けは、まだ断定せずに見たい題材だと思う。`
- `映画の話` -> `映画の話でいこう。普通に続けられる。`
- `お茶漬けの話` -> `お茶漬けの話でいこう。普通に続けられる。`

Live memory/history were cleared:

- `semantic_count=0`
- `episode_count=0`
- `sessions=0`

## Note

The live server restart was not completed because the escalation request was rejected by the usage-limit approval system. The running server may need a restart before these code changes are reflected in the browser.

## Follow-up: Qwen Question Ending Fix

After server restart, Qwen3 1.7B still produced replies ending in questions such as:

`次回はどんなゲームをプレイするか教えてくれないかな？`

Additional fixes:

- Rebuilt `agent/prompt_builder.py` again with clean Japanese prompt text.
- Made non-troubleshooting replies that end in `?` or `？` always trigger question repair.
- Added detection for Qwen-style phrases such as `次回は`, `どんな`, and `教えてくれ`.
- Restored tests to clean Japanese and added a regression test for the Qwen question-ending example.

Verification:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1
```

Result: 33 tests passed.

Prompt inspection for `FUSHIについてどう思う` showed clean Japanese instructions and `雑談では質問で終わらせない`.

Live server was restarted and checked with Qwen3 1.7B. `FUSHIについてどう思う` returned:

`FUSHIはまだ輪郭が薄いけど、話の中で育てるには悪くない題材だと思う。`

Live memory/history were cleared after verification:

- `semantic_count=0`
- `episode_count=0`
- `sessions=0`

## Follow-up: Restore Yachiyo Flavor

After stabilizing question endings, the persona became too neutral. Root cause:

- `yachiyo_spirit/persona_anchor.md` had mojibake again.
- `yachiyo_spirit/style_examples.jsonl` had mojibake again.
- Repair replies were too utilitarian and removed Yachiyo flavor.

Additional fixes:

- Restored `persona_anchor.md` with clean Japanese Yachiyo traits.
- Restored `style_examples.jsonl` with clean Japanese examples.
- Updated prompt wording so Yachiyo flavor appears as acceptance, playfulness, and margin rather than heavy lore.
- Added light Yachiyo markers to repair replies:
  - `ヤチヨ的には`
  - `ヤッチョ`
  - `なのです`
  - `キラキラ`
  - `だよ` / `だね`
- Added regression assertions that repaired casual replies keep light Yachiyo flavor.

Verification:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase1
```

Result: 33 tests passed.

Live server output after restart:

- `FUSHIについてどう思う` -> `FUSHIはまだ輪郭が薄いけど、話の中で育てるには悪くない題材だと思う。ちょっとキラキラしてるね。`
- `なんか疲れた` -> `それはしんどいね。今日は無理にがんばらず、だらっと話すくらいでいいよ、ヤチヨ的には。`

Live memory/history were cleared after verification:

- `semantic_count=0`
- `episode_count=0`
- `sessions=0`
