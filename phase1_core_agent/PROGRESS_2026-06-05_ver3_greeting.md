# 2026-06-05 Ver3 Greeting Update

## 変更

- `agent/llm_engine.py`
  - 純粋な挨拶入力を短絡処理し、`ヤオヨロー！` で始まる返答を優先
  - フォールバック側の挨拶返答も `ヤオヨロー！` に統一

- `agent/persona.py`
  - 挨拶の立ち上がりは `ヤオヨロー！` を優先してよい、という指示を追加

- `tests/test_phase1.py`
  - 挨拶の短絡処理と回帰ケースを追加

## 検証

- `.venv\Scripts\python.exe -m unittest tests.test_phase1`
  - `26 tests OK`

## 備考

- この版を `ver3` としてまとめる前提
