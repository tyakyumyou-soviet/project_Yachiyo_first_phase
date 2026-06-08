# 2026-06-08 Chat Stability Reset

## Goal

Qwen3 1.7B で再発していた会話崩壊を止める。

対象症状:

- 通常会話でツール名や `get_current_time` のような文字列が漏れる
- 不具合相談でも雑談・挨拶へ逃げる
- 文字化けした制御文が混ざる
- 長期メモリの壊れた要約が会話に注入される

## Root Causes

1. 通常チャット経路にツール契約が常時注入されていた
2. フォールバックがツールタグを直接返していた
3. 小型モデルにも重い多層プロンプトを毎ターン投入していた
4. 制御層に文字化け文字列が残っていた
5. 壊れた長期メモリが recall されていた
6. 後段で補正しても、生の崩れた文字列が先にストリーム表示されていた

## Changes

### Prompt path

- `agent/prompt_builder.py` を簡素化
- `qwen3:1.7b` は最小プロンプト経路へ変更
- 通常チャットから `Available Tools` を除去
- 不具合相談では「挨拶なしで本題に入る」を追加

### LLM engine

- `agent/llm_engine.py` を整理
- フォールバックからツールタグ出力を削除
- `normalize_yachiyo_output()` でツールタグと残留コマンド文字列を除去
- 失敗文言を正常な日本語へ修正

### Drift / recovery

- `agent/drift_detector.py` を整理
- 文字化けした禁止語判定を除去
- 回復命令文を正常化
- 壊れた返答に対する自己再生成依存をやめ、安全側返答を優先

### Memory

- `agent/memory_hub.py` を保守的に再実装
- 壊れた要約や文字化けメモリを recall 対象から除外
- 壊れた fact / episode を新規保存しないよう変更

### Runtime

- `main.py` の通常チャット経路からツールループを除去
- ストリーム中の生テキストをそのまま表示せず、整形後テキストを出す方式へ変更
- 不具合相談なのに雑談へ逃げた場合、短い実務返答へ差し替える安全弁を追加

## Verification

- `python -m unittest tests.test_phase1` -> 20 tests passed
- `scripts/inspect_prompt.py "スマホで送信できない" --json`
  - `qwen3:1.7b` の system prompt は約 634 chars
  - ツール契約なし
- UTF-8 の Python クライアントで `/chat/complete` を確認
  - 入力: `スマホで送信できない`
  - 出力: `送信イベントか通信経路のどちらかで止まっていそう。まずは押した直後にステータス表示かネットワークリクエストが動くか見て。`
- サーバー再起動後に `/health` で `qwen3:1.7b` active を確認

## Remaining Risk

- `qwen3:1.7b` 自体はロールプレイ耐性が弱い。安全弁なしではまだ雑談逃避を起こしうる。
- 既存 `sessions.json` の古い壊れた履歴は残っている。新規セッションでの確認を優先すべき。
- `thinking_summary` と `plan_summary` は固定文なので、不要なら次に削除対象。
