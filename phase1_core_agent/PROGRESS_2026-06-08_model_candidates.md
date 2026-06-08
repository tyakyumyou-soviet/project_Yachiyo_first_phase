# 2026-06-08 Local Roleplay Model Candidates

## Changes

- Installed `qwen3:1.7b` through the local Ollama API.
- Installed `qwen3:4b-instruct-2507-q4_K_M` through the local Ollama API.
- Installed `yuiseki/tinyswallow:1.5b` through the local Ollama API.
- Installed `hf.co/tensorblock/sarashina2.2-1b-instruct-v0.1-GGUF:Q2_K` through the local Ollama API.
- Removed `qwen3-vl:8b` from the local Ollama model store.
- Removed the `Qwen3-VL 8B` runtime profile from `model_manager.py`.
- Added runtime profiles for Qwen3 1.7B, Qwen3 4B Instruct 2507 Q4_K_M, TinySwallow 1.5B Instruct, and Sarashina2.2 1B Instruct Q2_K.
- Updated `README.md` and `YACHIYO_ROLEPLAY_SYSTEM_REVISION_PLAN_2026-06-08.md`.
- Changed the stale `OLLAMA_MODEL` fallback from deleted `qwen3-vl:8b` to `gemma4:e2b`.

## Notes

- Sarashina2.2 1B Instruct was requested as an instruct model. The desired Q4_K_M Hugging Face tag did not resolve through Ollama in this environment.
- The Hugging Face model page's Ollama example tag `Q2_K` installed successfully, so it is available as an initial latency and compatibility probe.
- If Sarashina is promising, retry Q4_K_M later using a local GGUF download plus Modelfile or another GGUF repository.

## Verification

- `GET http://127.0.0.1:11434/api/tags` confirmed the new models are present and `qwen3-vl:8b` is absent.
- `.venv\Scripts\python.exe -m unittest tests.test_phase1` passed: 16 tests.
- Restarted the FastAPI server on `0.0.0.0:8000`.
- `GET http://127.0.0.1:8000/models` confirmed all new profiles are `installed: true`.
- Browser verification confirmed the model selector shows the new candidates and no longer shows `Qwen3-VL 8B`.
