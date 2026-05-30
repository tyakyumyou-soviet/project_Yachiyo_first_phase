# LLM Switching

更新日: 2026-05-20

## 追加したこと

- `GET /models` で利用可能モデル一覧を返すようにした
- `POST /models/select` でアクティブモデルを切り替えられるようにした
- アクティブモデル状態を `data/model_state.json` に保存するようにした
- ブラウザ UI のヘッダーにモデル切り替えセレクタを追加した
- 軽量モデル向けに `Qwen2.5 3B` と `Gemma 3 1B` を導入した
- 会話履歴保存時に制御タグの残留を除去するようにした
- UI 側でも会話本文から制御タグを取り除いて表示するようにした

## 導入済みモデル

- `qwen3-vl:8b`
- `qwen2.5:3b-instruct`
- `gemma3:1b`

## 既定のアクティブモデル

- `Gemma 3 1B`
- 理由: 現在は最軽量の応答速度を優先するため

## 検証

- `.venv\Scripts\python.exe -m unittest tests.test_phase1`
  - 15 tests passed
- `.venv\Scripts\python.exe scripts\verify_model_switching.py`
  - `Qwen2.5 3B` で 1 ラリー成功
  - `Gemma 3 1B` で 1 ラリー成功
  - 検証ログを [data/model_switch_verification.json](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\data\model_switch_verification.json) に保存

## 補足

- 切り替え結果の正本は `/models` と `/health` の `active_model` で確認できる
- UI は `http://127.0.0.1:8000/` を開くと、そのままモデル切り替えとチャットができる
