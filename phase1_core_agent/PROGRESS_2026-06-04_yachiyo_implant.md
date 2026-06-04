# 2026-06-04 Yachiyo Persona Implant

## 目的

- `yachiyo_spirit/` の設計資料を、実際のランタイムプロンプトへ接続する
- まずは壊れにくい `Light` ベースでヤチヨ人格を移植する

## 実装

- `agent/persona.py`
  - `Yachiyo Light` 用の簡易プロンプトを、ヤチヨ人格の実行プロンプトへ更新
  - `Light` を既定モードにしつつ、人格の核、話し方、禁止事項を整理
  - `「あら」で話し始めない` を維持

- `agent/prompt_builder.py`
  - `load_character_profile()` を再接続
  - `yachiyo_spirit/Features_yachiyo.txt` を `Character notes` として system prompt に注入
  - モデル別に注入量を調整
    - `gemma3:1b`: 短め
    - `gemma4:e2b`: 中くらい
    - それ以外: やや長め

- `agent/llm_engine.py`
  - フォールバック返答を、完全な素の助手口調ではなく、薄いヤチヨ口調へ調整

- `tests/test_phase1.py`
  - `Character notes` 注入を確認するテストへ更新

## 検証

- `.venv\Scripts\python.exe -m unittest tests.test_phase1`
  - `25 tests OK`
- `/health`
  - character profile loaded
- `POST /chat/complete`
  - `こんにちは` への返答でヤチヨ寄りの応答を確認

## 運用判断

- アクティブモデルを `Gemma 4 E2B` に切り替え
- `Gemma 3 1B` より、人格移植後の応答安定性が高い前提で運用開始
