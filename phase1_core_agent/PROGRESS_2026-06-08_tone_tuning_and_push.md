# 2026-06-08 Tone Tuning And Push

## Goal

- `ヤオヨロー！` の出し過ぎを止める
- 質疑応答が尋問っぽくなる挙動を弱める
- 友達っぽい気楽な雑談トーンへ寄せる

## Changes

- `agent/prompt_builder.py`
  - 日本語の制御文を全面的に正常化
  - `ヤオヨロー！` は挨拶入力以外では使わないと明記
  - 雑談では質問を必要なときだけにすると明記
  - 不具合相談と雑談のモード指示を整理
- `agent/llm_engine.py`
  - 文字化けした日本語を全修正
  - 挨拶ショートリプライを `こんにちは` 系だけに限定
  - 雑談フォールバックを柔らかい会話寄りに変更
- `yachiyo_spirit/persona_anchor.md`
  - 口調ルールを正常な日本語で再定義
  - 「毎回ヤオヨローしない」「雑談で質問連発しない」を追加
- `yachiyo_spirit/style_examples.jsonl`
  - 挨拶、不具合相談、雑談の例を正常な日本語で更新
- `yachiyo_spirit/lorebook.jsonl`
  - 挨拶条件、禁止語尾、雑談トーン、不具合相談の指針を更新
- `main.py`
  - 非挨拶入力で先頭の `ヤオヨロー` を除去する後段ガードを追加
  - 疲れた、だるい、眠い、ひま、なんか、のような短い雑談に対しては尋問風にならないように柔らかい返答へ差し替えるガードを追加
- `tests/test_phase1.py`
  - 日本語仕様に合わせて全面更新
  - 非挨拶で `ヤオヨロー` が外れること
  - カジュアル返答が質問過多を避けること
  - 既存 API と履歴削除機能が動くことを検証

## Verification

- `python -m unittest tests.test_phase1` -> 24 tests passed
- `/chat/complete` with `なんか疲れた`
  - `それはきついな。今日は無理にがんばらず、だらっと話すくらいでいいよ。`
- `/chat/complete` with `こんにちは`
  - `ヤオヨロー！今日はどうする？`

## Note

- 実行中サーバーの active model は検証時点で `qwen3:4b-instruct-2507-q4_K_M` だった。
- 必要なら push 前後で `qwen3:1.7b` に戻せる。
