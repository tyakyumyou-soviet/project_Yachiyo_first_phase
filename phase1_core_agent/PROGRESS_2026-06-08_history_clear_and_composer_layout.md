# 2026-06-08 History Clear And Composer Layout

## Goal

- 過去の会話履歴を一括削除できるようにする
- 削除ボタンを UI に追加する
- モデル選択欄を入力欄の近くへ移設する

## Changes

- `main.py`
  - `SessionStore.clear_all()` を追加
  - `POST /history/clear` を追加
  - この API は保存済みセッションと memory DB を両方クリアする
- `agent/memory_hub.py`
  - `clear_all()` を追加
- `app_shell.html`
  - モデル選択をヘッダから composer へ移動
  - `履歴削除` ボタンを追加
  - 履歴削除後は新しい `sessionId` を払い出し、画面ログを空にする
  - モバイル幅でも composer 内に縦積みされるように調整
- `tests/test_phase1.py`
  - `SessionStore.clear_all()` のテストを追加
  - `POST /history/clear` のテストを追加

## Verification

- `python -m unittest tests.test_phase1` -> 22 tests passed
- `POST /history/clear` -> `{"status":"ok"}`
- `/health`
  - `memory.semantic_count = 0`
  - `memory.episode_count = 0`
  - `sessions = 0`
- active model restored to `qwen3:1.7b`

## Notes

- 履歴削除は「現在の表示ログだけ」ではなく、保存済みセッションと長期メモリも消す。
- そのため、過去会話からの recall 汚染も同時に止まる。
