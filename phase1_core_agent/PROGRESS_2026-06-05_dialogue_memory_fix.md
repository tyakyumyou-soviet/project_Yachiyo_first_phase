# 2026-06-05 Dialogue And Memory Fix

## 目的

- 途中から同じことを繰り返す症状を減らす
- 会話履歴をちゃんと覚えるようにする
- 短い挨拶で古い `memory_recall` を引っ張りすぎないようにする

## 実装

- `main.py`
  - `SessionStore` を JSON 永続化対応に変更
  - `data/sessions.json` にセッション履歴と completed turns を保存
  - 起動時に既存セッションを復元
  - 短い挨拶や極端に短い入力では `memory_hub.recall()` を走らせない
  - 直前の assistant 返答とほぼ同じ文が出た時は、同文反復を避ける救済返答へ差し替え

- `config.py`
  - `SESSION_STORE_PATH` を追加

- `tests/test_phase1.py`
  - セッション永続化
  - 短い挨拶で recall しない判定
  - 反復判定
  を追加

## 検証

- `.venv\Scripts\python.exe -m unittest tests.test_phase1`
  - `30 tests OK`
