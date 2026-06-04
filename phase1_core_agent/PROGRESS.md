# 進行状況・実装ログ (Phase 1)

最終更新: 2026-05-30

## 現在の状態

Phase 1 を単体で運用・検証しやすい形まで実装済み。SSE、WebSocket、SQLite 記憶、ツール実行、開発フォールバック、複数 LLM 切り替え、キャラクタープロファイル注入、テストまで揃っている。

## 実装済み

- FastAPI アプリを [main.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\main.py) に実装
- `GET /health` で Ollama 状態、記憶件数、セッション数を返すようにした
- `GET /tools` と `GET /sessions` を追加
- `GET /` にブラウザ用チャット UI を追加
- `GET /models` と `POST /models/select` を追加し、モデル切り替えを実装
- `POST /sessions/{session_id}/reset` を追加
- `POST /chat` を SSE の逐次配信に変更
- `WebSocket /ws/chat` を実装し、接続時にセッション ID を返すようにした
- [agent/llm_engine.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\agent\llm_engine.py) に Ollama 優先 + 開発フォールバックを実装
- [agent/stream_parser.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\agent\stream_parser.py) で `thinking_summary` / `plan_summary` / `text_chunk` / `emotion_trigger` / `motion_trigger` / `tool_pending` を分離
- [agent/memory_hub.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\agent\memory_hub.py) を SQLite ベースへ変更
- [agent/prompt_builder.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\agent\prompt_builder.py) を整理し、履歴と記憶を安全にトリムするようにした
- [agent/character_profile.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\agent\character_profile.py) を追加し、`Features_yachiyo.txt` を応答プロンプトへ注入するようにした
- [tools/pc_control.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\tools\pc_control.py) に `list_directory` / `read_text_file` / `write_text_file` / `delete_file` を実装
- [tools/hitl_manager.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\tools\hitl_manager.py) に destructive tool 向け承認ロックを実装
- [tools/web_search.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\tools\web_search.py) に DuckDuckGo HTML + ページ本文断片取得の軽量検索を実装
- [tools/tool_registry.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\tools\tool_registry.py) に利用可能ツール定義を集約
- [tests/test_phase1.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\tests\test_phase1.py) を拡張
- [README.md](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\README.md) を更新
- [LLM_SWITCHING.md](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\LLM_SWITCHING.md) を追加

### 2026-05-30 八千代キャラクタープロファイル適用

- [Features_yachiyo.txt](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\Features_yachiyo.txt) を自動読み込みするようにした
- `build_messages()` のシステムプロンプトに `Character profile` として特徴ファイルを注入
- `/health` に `character_profile.loaded/chars/truncated/path` を追加
- 署名的な口調を引用符つきのラベルとして使わないようにプロンプトを調整
- `.venv\Scripts\python.exe -m unittest tests.test_phase1` を実行
  - 16 件のテストが成功
- 実 LLM で 1 ラリー確認
  - `神々のみんな` など、特徴ファイル由来の呼びかけが返答に反映されることを確認

### 2026-05-30 Gemma 向けヤチヨ口調安定化

- `Gemma 3 1B` が短文雑談で汎用的または崩れた返答を返す問題を確認
- [agent/persona.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\agent\persona.py) の口調アンカーを整理
- [agent/llm_engine.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\agent\llm_engine.py) に短文日常会話用のヤチヨ応答レイヤーを追加
- `Gemma 3 1B` の出力が長すぎる、三点リーダーを繰り返す、違和感の強い断片を含む場合はフォールバックへ回す品質ガードを追加
- `.venv\Scripts\python.exe -m unittest tests.test_phase1` を実行
  - 18 件のテストが成功
- 実会話で以下を確認
  - `こんにちは`
  - `うんちしたい`
  - `今度ピクニックいくんだー`
  - `スマホ壊れちゃった`

### 2026-05-20 複数 LLM 対応

- [model_manager.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\model_manager.py) を追加
- `qwen3-vl:8b`、`qwen2.5:3b-instruct`、`gemma3:1b` の 3 モデルをプロファイル化
- アクティブモデル状態を `data/model_state.json` に永続化
- UI のヘッダーにモデルセレクタを追加
- 会話履歴保存時と UI 表示時に制御タグ残留を除去するよう修正
- [scripts/verify_model_switching.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\scripts\verify_model_switching.py) を追加

## 検証結果

### 2026-05-19

- `.venv\Scripts\python.exe -m unittest tests.test_phase1` を実行
- 7 件のテストが成功
- `.venv\Scripts\python.exe main.py` で起動確認
- `GET http://127.0.0.1:8000/health` が以下を返すことを確認
  - `status: ok`
  - `ollama: error` または `ok/degraded`
  - `memory`
  - `sessions`
- `POST /chat` で以下のイベントが逐次返ることを確認
  - `thinking_summary`
  - `plan_summary`
  - `tool_pending`
  - `tool_result`
  - `text_chunk`
  - `emotion_trigger`
  - `motion_trigger`

### 2026-05-19 LLM セットアップ

- `winget` で `Ollama.Ollama 0.24.0` をインストール
- `ollama version is 0.24.0` を確認
- `ollama pull qwen3-vl:8b` を実行
- `ollama list` で `qwen3-vl:8b` が `6.1 GB` として登録されたことを確認
- `GET http://127.0.0.1:8000/health` が以下を返すことを確認
  - `status: ok`
  - `ollama.status: ok`
  - `ollama.detail: model qwen3-vl:8b available`

### 2026-05-20 軽量モデル追加と切り替え確認

- `ollama pull qwen2.5:3b-instruct` を実行
- `ollama pull gemma3:1b` を実行
- `GET http://127.0.0.1:8000/models` で 3 モデルすべて `installed: true` を確認
- `POST /models/select` で `Qwen2.5 3B` と `Gemma 3 1B` の切り替えを確認
- `.venv\Scripts\python.exe -m unittest tests.test_phase1` を実行
  - 15 件のテストが成功
- `.venv\Scripts\python.exe scripts\verify_model_switching.py` を実行
  - `Qwen2.5 3B` で 1 ラリー成功
  - `Gemma 3 1B` で 1 ラリー成功
  - 検証ログを `data/model_switch_verification.json` に保存

## 現在の運用状態

- Phase 1 サーバーは起動可能
- Ollama 本体はインストール済み
- `qwen3-vl:8b`、`qwen2.5:3b-instruct`、`gemma3:1b` はローカルへダウンロード済み
- 既定のアクティブモデルは `Gemma 3 1B`
- 実 LLM 接続は health と 1 ラリー会話で確認済み

## 補足

- Ollama 本体はこの検証時点では未起動だったため、`/health` の Ollama 状態は `error` になった
- それでも `ENABLE_DEV_FALLBACK=1` により、Phase 1 単体の開発確認は継続できる
- 記憶層は JSON から `data/memory.sqlite3` へ移行済み
- 破壊的ツールはターミナル承認を要求する

## 次の候補

- Phase 2 UI との WebSocket 契約テストを追加
- 記憶検索のスコアリング強化
- `search_web` の要約品質と耐障害性の強化

## 2026-06-03 Yachiyo Light プロンプト初版

- `yachiyo_spirit/` に人格設計資料、抽出ガイド、評価セット、実プロンプト初版を追加
- `agent/persona.py` を通常AIモードから `Yachiyo Light` 用の短い実行プロンプトへ変更
- `app_shell.html` の表示名を `Yachiyo Light` に変更
- `config.py` の既定ホストを `0.0.0.0` に変更し、Tailscaleアクセス時も起動しやすくした
- `Features_yachiyo.txt` の既定参照先を `yachiyo_spirit/Features_yachiyo.txt` に変更
- Gemma 1B の語尾断片出力を検知し、1回だけ修復再生成する品質ガードを追加
- テストが `/models/select` 後に `data/model_state.json` を汚さないよう、モデル状態の復元処理を追加
- `.venv\Scripts\python.exe -m unittest tests.test_phase1` で 24 件成功
- 実測では Gemma 1B は文脈追従が弱く、Qwen2.5 3B のほうが Yachiyo Light の会話品質が安定したため、現在のアクティブモデルは `qwen25_3b`

## 2026-06-03 Gemma 4 E2B 追加

- Ollama の正式タグ `gemma4:e2b` を確認
- `model_manager.py` のプロファイル一覧へ `Gemma 4 E2B` を追加
- `README.md` の導入手順と利用可能モデル一覧へ `gemma4:e2b` を追記
