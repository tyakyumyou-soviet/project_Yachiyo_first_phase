# 2026-06-08 Model Cleanup

## Removed Models

Removed from local Ollama:

- `qwen2.5:3b-instruct`
- `gemma4:e2b`
- `yuiseki/tinyswallow:1.5b`
- `hf.co/tensorblock/sarashina2.2-1b-instruct-v0.1-GGUF:Q2_K`

Removed from app runtime profiles:

- `Qwen2.5 3B`
- `Gemma 4 E2B`
- `TinySwallow 1.5B Instruct`
- `Sarashina2.2 1B Instruct Q2_K`

## Remaining Models

- `gemma3:1b`
- `qwen3:1.7b`
- `qwen3:4b-instruct-2507-q4_K_M`

## Runtime State

- Default model profile is now `qwen3_17b`.
- Saved active model state is now `qwen3_17b`.

## Verification

- `GET http://127.0.0.1:11434/api/tags` confirmed only `gemma3:1b`, `qwen3:1.7b`, and `qwen3:4b-instruct-2507-q4_K_M` remain.
