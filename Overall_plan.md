# Project Yachiyo Overall Plan

作成日: 2026-05-07

この文書は、`FEASIBILITY_REVIEW.md`、`PLAN_CHANGE_SPEC_2026-05-07.md`、`PLAN_REVISION_PROPOSAL.md` を統合した正式な総合計画書。今後の判断、実装順序、技術選定、各フェーズの変更方針はこの文書を基準にする。

## 1. 前提

| 項目 | 決定 |
|:---|:---|
| 実行環境 | 個人のWindows PCを第一ターゲットにする。 |
| GPU | NVIDIA RTX 3060。専用GPUメモリ 12GB、共有GPUメモリ 8GB。 |
| GPUメモリ方針 | 性能予算は専用VRAM 12GBのみ。共有GPUメモリ8GBはクラッシュ回避の保険で、常用前提にしない。 |
| 完全ローカル無料の意味 | 外部API課金、サブスク、クラウド推論を使わない。インターネット接続、Web検索、初回モデルDL、LAN/Tailscale利用は禁止しない。 |
| セキュリティ優先度 | 破壊的操作のHitLは維持する。HTTPSや厳密なネットワーク防御より、まず統合して動くことを優先する。 |
| フェーズの位置づけ | Phase 1〜3は技術実証とPhase 4統合用パーツ作成。Phase 4で1つのアプリ/システムとして統合する。 |
| 声質R&D | 完全個人・非公開・非配布・非商用前提で進めてよい。本体MVPの必須条件にはしない。 |

## 2. プロジェクト意図

Project Yachiyo の本質は「キャラクター付きチャットボット」ではなく、ローカルで動く個人用AI OSレイヤー。

- 人格: 継続的に関係性を持つ会話体験。
- 身体: VRMアバターによる存在感。
- 声: 低遅延TTSとリップシンク。
- 記憶: 長期関係性とタスク文脈の保持。
- 行為: PC操作、検索、ファイル処理などの実行。
- 安全: Human-in-the-loop と監査可能性。

最初から理想形をすべて狙うとPhase 3/4で難度が跳ねるため、まずは「テキスト秘書 + 3Dリアクション + 安全なツール実行」をMVPとして固める。その後、音声品質、声質R&D、長期人格最適化を段階的に引き上げる。

## 3. 最重要変更

| 領域 | 旧計画 | 新方針 |
|:---|:---|:---|
| LLM | `llama3:8b-instruct-q4_K_M` 固定 | 現行本命は `Qwen3-VL 8B`。通常会話・画像/スクショ理解・ファイル参照の中核モデルとして使う。ただし、リアルタイム性をさらに重視する場合に備え、`Gemma 4 26B A4B + MTP` を将来の移行候補として比較可能な設計を保つ。 |
| 制御形式 | 会話文中のXMLタグ | Ollama tool calling / structured outputs + `ControlPlanner` のJSONイベント。 |
| 記憶DB | ChromaDB + MiniLM | LanceDB第一候補。最軽量候補はSQLite + sqlite-vector/sqlite-vec。 |
| STT | Web Speech API固定 | MVPはWeb Speech API。ローカル候補は whisper.cpp / Moonshine / Vosk。 |
| TTS | Style-Bert-VITS2一本 | GPT-SoVITSを先行検証。満足できなければStyle-Bert-VITS2へ移行。F5-TTS / IndexTTS2 / VOICEVOXも比較枠。 |
| HTTPS/PWA | mkcert前提 | 後段対応。まずlocalhost/LAN/Tailscale IPで動けばよい。 |
| 統合 | `start_yachiyo.bat` | `yachiyo_supervisor.py` + bat wrapperでWindows上の4プロセスを起動・監視。 |

## 4. フィジビリティ評価

| 領域 | 評価 | コメント |
|:---|:---:|:---|
| Phase 1 Core Agent | 高 | FastAPI + Ollama + ローカルDBで実現可能。XML廃止とtool schema化で安定性が上がる。 |
| Phase 2 Avatar UI | 高 | Vite + React + R3F + three-vrm は妥当。VRM表情名差分、ボーン初期姿勢、モバイルWebGL性能に注意。 |
| Phase 3 TTS | 中 | Style-Bert-VITS2は妥当。声質再現、学習データ品質、低遅延、GPU競合が山。 |
| Phase 4 Integration | 中 | 4プロセス統合は可能。Windows supervisor、VRAM実測、fallback modeが必要。 |
| 完全ローカル無料 | 高 | 外部API課金なしという意味なら成立しやすい。Web検索や初回DLは許容。 |
| リモートアクセス | 中〜高 | まずlocalhost/LAN/Tailscale IPで動かす。HTTPS/PWAは必要になったら対応。 |

## 5. MVPと優先順位

優先順位:

1. 安全なローカルエージェント基盤。
2. テキスト会話と記憶。
3. VRMアバター反応。
4. 音声入出力。
5. 声質R&D。
6. リモートHTTPS/PWA。

MVP:

| 優先度 | 内容 |
|:---:|:---|
| P0 | テキストチャット、Ollama応答、WebSocketストリーミング、記憶検索、HitLつき安全ツール。 |
| P1 | VRM表示、表情、簡易モーション、チャットUI、Phase 1との最小統合、localhost/LANアクセス。 |
| P2 | TTS再生、リップシンク、音声入力、必要ならPWA。 |
| P3 | 声質学習、低遅延TTS、長期人格最適化。 |

Phase 2で行う最小統合:

- Phase 1のWebSocketに接続し、UI単体ではなく「脳と身体が繋がった状態」で動作確認する。
- `text_chunk` をチャットUIへ反映する。
- `emotion_trigger` を受けてVRM表情を切り替える。
- `motion_trigger` を受けて簡易モーションを再生する。
- `thinking_summary` などの状態イベントを小さなパネルへ表示する。

Phase 2ではまだ無理に入れないもの:

- TTS本番統合の完成形
- 高精度リップシンクの仕上げ
- PWA/HTTPSの本格運用
- 4プロセス常時同居の最終チューニング

## 6. ハードウェア判断

WindowsではGPU専用メモリを使い切ると共有GPUメモリへ退避する場合がある。ただし共有メモリはシステムRAM経由で、専用VRAMより大幅に遅い。LLMやTTSでは、共有メモリに乗った瞬間に「動くが会話テンポが壊れる」状態になりやすい。

| メモリ | 扱い |
|:---|:---|
| 専用VRAM 12GB | 実運用の性能予算。ここに収まる構成だけを標準運用にする。 |
| 共有GPUメモリ 8GB | OOM回避の保険。使われ始めたら設定を落とすサイン。 |

推奨 runtime mode:

| モード | LLM | TTS | STT | 想定 |
|:---|:---|:---|:---|:---|
| Normal | Qwen3-VL 8B, 8k〜16k | GPT-SoVITS | Web Speech API | 標準 |
| Voice Stable | Qwen3-VL 8B, 8k | GPT-SoVITS | whisper.cpp CPU または Web Speech API | 音声安定優先 |
| Text Rich | Qwen3-VL 8B, 16k〜32k | OFF | OFF | 長文・記憶重視 |
| R&D TTS | Qwen3-VL 8B, 8k | GPT-SoVITS/F5-TTS/IndexTTS2 | OFF | TTS比較 |
| Reasoning | Qwen3-VL 8B, 16k〜32k | OFF | OFF | 重い思考の実験 |

## 7. Phase 1: Core Agent

### 7.1 LLM

メインモデルは `Qwen3-VL 8B` に一本化する。

ただし、現時点での意味は「開発を進める基準モデルとして固定する」であり、将来永久に他モデルを排除するという意味ではない。リアルタイム性、tool calling安定性、RTX3060上の実効速度で優位が確認できた場合、`Gemma 4 26B A4B + MTP` へ移行またはruntime mode別に併用する余地は残す。

理由は、ヤチヨにClaude Code/Codex的な自律ファイル参照、画像添付、スクリーンショット理解、GUI理解を持たせる場合、最初からテキストと画像を同じモデルで扱える方が設計が単純になるため。`LLM-jp-4 8B` は日本語テキスト会話では有力だが、画像そのものは読めない。モデル切替・Vision分業を最小化するため、通常会話・画像理解・スクショ理解・ファイル参照判断の中核を `Qwen3-VL 8B` に統一する。

比較候補:

| 候補 | 特徴 | RTX3060での扱い |
|:---|:---|:---|
| Qwen3-VL 8B | テキスト + 画像。Ollamaで約6.1GB、256K context、OCR/GUI理解/画像QA | 採用。唯一のメインLLM |

`LLM_PROFILE` は残すが、初期実装では `qwen3-vl:8b` の設定だけを定義する。将来どうしても日本語会話品質が不足した場合のみ、LLM-jp-4等のテキスト専用モデルを追加検証する。

また、将来の `Gemma 4 26B A4B + MTP` 比較に備え、`LLM_PROFILE`、推論アダプタ、tool schema、ControlPlanner入出力は、可能な限りモデル固有形式へ密結合しないように保つ。

評価項目:

| 項目 | 見ること |
|:---|:---|
| 日本語人格会話 | Qwen3-VL 8Bでヤチヨ口調、柔らかさ、雑談継続、固有語が十分か。 |
| tool/JSON適性 | Ollama tool calling、structured outputs、JSON破損率。 |
| VRAM/速度 | RTX3060専用VRAM12GBでTTS同居できるか、tokens/sec。 |
| 長文脈 | 8k/16k/32k以上で記憶を入れた時の安定性。 |
| 思考サマリ | chain-of-thought全文ではなく、ユーザー向け `thinking_summary` を作れるか。 |
| 画像/ファイル | 画像/スクショはQwen3-VLへ直接、文書は抽出ツール経由で扱えるか。 |

決定:

- 通常会話: `Qwen3-VL 8B`
- ツール/JSON制御: `Qwen3-VL 8B`
- 画像/スクショ理解: `Qwen3-VL 8B`
- 自律ファイル参照判断: `Qwen3-VL 8B`
- テキスト/文書抽出: `FileIngestionTool`

### 7.1.1 画像/ファイル対応

画像やスクリーンショットは `Qwen3-VL 8B` が直接読む。PDF、Word、Excel、コード、CSVなどのファイルは、モデルへ丸投げせず `FileIngestionTool` でテキスト抽出・chunk化してから `Qwen3-VL 8B` に渡す。

| 入力 | 実現方法 |
|:---|:---|
| `.txt`, `.md`, `.json`, `.csv` | Pythonで直接読み、必要なら要約して通常LLMへ渡す。 |
| `.pdf`, `.docx`, `.xlsx` | ローカル抽出ツールでテキスト化し、必要な範囲だけLLMへ渡す。 |
| 画像 | Ollama Vision APIで `Qwen3-VL 8B` に渡す。 |
| スクリーンショット | `Qwen3-VL 8B` に渡し、UI要素や文字を読む。 |
| 大きいファイル群 | chunk化、embedding、LanceDB登録後に検索して渡す。 |

MCPはファイルアクセスやツール実行の入り口としては使えるが、画像理解そのものはMCPでは解決しない。画像理解は `Qwen3-VL 8B` が担当する。文書ファイルは抽出ツールで整えてから同じ `Qwen3-VL 8B` に渡す。

### 7.1.2 Claude Code / Codex的な自律ファイル参照

ヤチヨには、Claude CodeやCodexのように、ユーザーが毎回ファイルを貼り付けなくても、自律的にワークスペース内のファイルを探し、読み、必要なら編集提案する機能を持たせる。

`Qwen3-VL 8B` 一本化により、LLMのモデル切替は原則不要にする。バックエンドの `Agent Orchestrator` はモデル切替ではなく、ファイル取得・抽出・OCR/画像入力形式への整形・HitLを管理する。

```text
User: 「この機能を直して」
  -> Main LLM: 何を調べるべきか計画
  -> ToolRouter: rg / file_read / list_files を実行
  -> FileIngestionTool: ファイル種別を判定
       ├─ text/code/markdown -> 直接テキスト抽出
       ├─ pdf/docx/xlsx -> ローカル抽出してテキスト化
       └─ png/jpg/screenshot -> Qwen3-VL 8Bへ画像入力
  -> Qwen3-VL 8B: 画像/OCR/UI理解
  -> Main LLM: 観測結果を受け取り、次の調査や修正案を決める
  -> HitL: 破壊的操作・書き込み前に承認
```

このため、メインLLMは「別の画像モデルへ切り替える」必要がない。メインLLMである `Qwen3-VL 8B` が `inspect_file(path)` や `read_workspace_file(path)` のような高レベルツールを呼び、ToolRouterがファイル種別に応じて、テキスト抽出、画像入力、LanceDB登録を行う。

#### 自律参照時のツール設計

| ツール | 役割 | モデル選択 |
|:---|:---|:---|
| `list_files(root, pattern)` | ファイル一覧を取得 | モデル不要 |
| `search_files(query, glob)` | `rg` 相当の全文検索 | モデル不要 |
| `inspect_file(path)` | ファイル種別を判定し、要約/抽出/OCRする | Orchestratorが自動選択 |
| `read_text_file(path)` | テキスト/コードを読む | Main LLMへ返す |
| `read_document(path)` | PDF/DOCX/XLSXを抽出 | 抽出ツール + Main LLM |
| `inspect_image(path)` | 画像/スクショを読む | Qwen3-VL 8B |
| `index_files(paths)` | 大量ファイルをchunk化してLanceDB登録 | Embedding + LanceDB |
| `propose_edit(path, diff)` | 編集案を生成 | Main LLM |
| `apply_edit(path, diff)` | 実ファイル変更 | HitL必須 |

#### 添付ファイルと自律参照の違い

| ケース | 処理 |
|:---|:---|
| ユーザーが画像を添付 | `InputRouter` が画像と判定し、VisionAdapterへ渡す。 |
| ユーザーがPDFを添付 | `FileIngestionTool` が抽出し、必要箇所だけMain LLMへ渡す。 |
| ヤチヨが自律的に画像を見つける | `inspect_file(path)` の内部でVisionAdapterが呼ばれる。 |
| ヤチヨが自律的にコードを読む | `search_files` / `read_text_file` の結果をMain LLMへ戻す。 |

つまり、添付でも自律参照でも入口が違うだけで、最終的には同じ `InputRouter` / `FileIngestionTool` / `VisionAdapter` を通る。

#### モデル切替の責務

- LLM自身: 「このファイルを確認したい」「画像を説明してほしい」とツールを呼ぶ。
- Agent Orchestrator: ファイル種別と目的に応じて、抽出ツール、画像入力、LanceDB登録、HitLを選ぶ。
- ToolRouter: 実際のファイル読み取り、検索、Vision API呼び出し、結果整形を行う。
- Main LLM: 結果を観測として受け取り、次の推論や編集案を作る。

これにより、モデル切替問題を最小化し、`Qwen3-VL 8B` を中心に再現性のある自律ファイル参照を実現する。

### 7.1.3 Phase 2への最小接続

Phase 1はPhase 4まで待たず、Phase 2の段階で最小限の接続先として使う。少なくとも次のイベントをWebSocketで安定送出できることをPhase 1完了条件の一部に含める。

- `text_chunk`
- `emotion_trigger`
- `motion_trigger`
- `thinking_summary`
- `tool_pending` または同等の状態イベント

### 7.2 XML制御をやめる理由

旧案では、LLMが本文に以下のようなタグを混ぜる。

```xml
ヤオヨロー！<emotion intensity="0.8">smile</emotion>今日は元気そうだね。<motion>nod</motion>
```

これは分かりやすいが、タグ破損、未完成タグのTTS混入、ツール引数の型検証不足、本文/制御/ツールの混在が起きやすい。

新方針では役割を分離する。

- 会話本文: プレーンテキストとしてストリーミング。
- ツール実行: Ollama tool callingでJSON schemaに従って呼ぶ。
- 表情/動作: structured outputsまたは `ControlPlanner` がJSON `ControlPacket` を生成。
- TTS: 常にプレーンテキストだけ受け取る。

tool calling例:

```json
{
  "name": "file_read",
  "arguments": {
    "path": "C:/Users/example/memo.txt"
  }
}
```

ControlPlanner出力例:

```json
{
  "sentence_id": "s-001",
  "emotion_trigger": {"type": "smile", "intensity": 0.8},
  "motion_trigger": {"type": "nod"}
}
```

メリット:

- JSON schemaで引数と許可値を検証できる。
- 危険ツールだけHitLへ回せる。
- TTSにタグが混ざらない。
- UIには検証済み `ControlPacket` だけ送れる。
- 将来TTS感情制御を入れる時も制御イベントを再利用できる。

### 7.3 思考過程UI

モデル内部の完全なchain-of-thought全文をそのまま表示する設計は推奨しない。代わりに、ユーザーに見せるための短い状態サマリを表示する。

表示候補:

- `thinking_summary`: 「予定削除なので確認が必要か判断中」
- `tool_pending`: 「file_write 実行前に承認待ち」
- `memory_recall`: 「以前の好み情報を2件参照」
- `plan_summary`: 「まず検索してから要約する」

FastAPI側が「今どの段階か」を状態イベントとして送り、UIが小さな状態パネルに表示する。長い推論や調査時だけ `plan_summary` を更新する。

### 7.4 追加/変更モジュール

```text
phase1_core_agent/
├── agent/
│   ├── model_profiles.py
│   ├── control_planner.py
│   ├── tool_router.py
│   ├── audit_log.py
│   ├── memory_store.py
│   └── memory_hub.py
└── data/
    ├── yachiyo.sqlite
    └── memory/
```

`stream_parser.py` は主役から外す。XML互換が必要な場合のみlegacy adapterとして残す。

## 8. 長期記憶と忘却

全情報を常にRAGへ入れない。重要度、使用頻度、最近使ったか、感情的重みで「思い出しやすさ」を変える。

### 8.1 記憶レイヤー

| レイヤー | 内容 | 検索頻度 |
|:---|:---|:---|
| working_memory | 直近会話、現在タスク | 毎回 |
| active_memory | よく使う好み、名前、進行中タスク | 毎回〜高頻度 |
| latent_memory | 最近使っていないが保存する記憶 | 必要時だけ |
| archive_memory | 古い会話要約、低重要度ログ | 明示検索時だけ |

### 8.2 記憶スキーマ

```text
memory_items
  id
  user_id
  kind: preference | profile | event | task | relationship | correction
  subject
  predicate
  object
  text
  confidence
  source_turn_id
  created_at
  last_seen_at
  expires_at
  privacy_level
  status: active | superseded | forgotten
```

### 8.3 忘却スコア

エビングハウスの忘却曲線を参考に、時間経過で想起スコアを下げる。ただし、再利用された記憶は強化する。

```text
recall_strength = base_importance
                * exp(-days_since_last_used / retention_days)
                + usage_count_bonus
                + emotional_weight
```

運用:

- 想起スコアが高い記憶だけ通常RAGに入れる。
- 低い記憶はDBには残すが、毎回のプロンプトには入れない。
- 関連話題が出た時だけ latent/archive から復帰させる。
- 「忘れて」と言われた記憶は `forgotten` にして通常検索から除外する。
- 矛盾時は自動上書きせず、新しい記憶として追加して検索時に解決する。

### 8.4 DB選定

軽さ・速さ・Windows個人PC運用を優先する。

| 候補 | 長所 | 短所 | 判断 |
|:---|:---|:---|:---|
| LanceDB | embedded、ベクトル検索、full-text/BM25、hybridが一体 | Chromaほど情報が多くない | 第一候補 |
| SQLite + sqlite-vector/sqlite-vec | 単一ファイル、低メモリ、バックアップ容易 | 日本語全文検索やRAG機能は自作が増える | 最軽量候補 |
| ChromaDB | 実装が簡単 | 長期運用の柔軟性はLanceDBに劣る可能性 | fallback |
| Qdrant | 高機能、hybrid/filter/UIが強い | 別プロセスが増える | 後段候補 |

Embeddingは `Qwen3-Embedding-0.6B` を品質候補、MiniLMを軽量fallbackにする。Rerankは `Qwen3-Reranker-0.6B` またはLLM rerankを後段で検証する。

## 9. Phase 2: Avatar/UI

Phase 2は、Phase 4統合で使うUI/アバターパーツの実証と作成を行う。

主要方針:

- VRM描画は `@pixiv/three-vrm` + R3Fを継続。
- LLM本文中のXMLタグを直接解釈しない。
- Phase 1の `ControlPlanner` が送る検証済みJSON `ControlPacket` を受け取る。
- 状態管理はContextだけでなくZustandを検討する。
- 表情名はモデル依存なので `expressionMap.json` で外部設定化する。
- モーションも `motionPresets.json` などで設定化する。
- WebGPUは後段の実験トグル。まずWebGL2で動かす。

音声入力:

- `SpeechProvider` インターフェースにする。
- MVPは `BrowserWebSpeechProvider`。
- ローカルSTTは `ServerWhisperCppProvider`。
- 比較枠は `MoonshineProvider` / `VoskProvider`。

思考過程UI:

- `thinking_summary`
- `plan_summary`
- `tool_pending`
- `memory_recall`

これらを小さな状態パネルに表示する。

## 10. Phase 3: Voice/TTS

### 10.1 TTSGateway

TTSは最初からGateway化し、エンジン差し替え可能にする。優先順は `GPT-SoVITS` → `Style-Bert-VITS2`。まずGPT-SoVITSで月見ヤチヨ/早見沙織さんにかなり近い声が出るかを検証し、満足できない場合にStyle-Bert-VITS2で本格学習へ進む。

```json
{
  "text": "ヤオヨロー！",
  "engine": "gpt_sovits",
  "voice_id": "yachiyo_safe_v1",
  "style": "auto",
  "speed": 1.0,
  "format": "wav"
}
```

### 10.2 TTS候補

| 技術 | 位置づけ | 期待 | 注意 |
|:---|:---|:---|:---|
| GPT-SoVITS | 第一検証エンジン | 5秒zero-shot、1分few-shot、日本語対応、WebUI/前処理が強い。少量素材で似るか早く試せる | VRAM同居、長文安定性、API統合を実測 |
| Style-Bert-VITS2 | 第二候補/本格学習 | GPT-SoVITSで満足できない場合の本命学習。日本語品質、辞書登録、キャラクター音声学習が強い | データ品質と学習工程が支配的 |
| F5-TTS | 方式比較 | Flow Matching系、自然さ、少量参照、ONNX派生の将来性 | 日本語・低遅延・Windows運用は実測 |
| IndexTTS2 | 感情/時間制御比較 | 感情と話者性の分離、発話時間制御、リップシンク適性 | 重い可能性、ライセンス/日本語品質確認 |
| VOICEVOX | fallback | 安定した日本語TTS、実装容易 | ヤチヨ専用声質ではない |

検証順:

1. GPT-SoVITSで5秒参照、1分few-shot、可能なら追加データで声質を確認する。
2. GPT-SoVITSの声質、安定性、低遅延、VRAM同居、API統合が満足ならPhase 4のTTS本採用候補にする。
3. GPT-SoVITSで声質や安定性が足りない場合、Style-Bert-VITS2へ移行する。
4. IndexTTS2は感情/発話時間制御の比較、F5-TTSは方式違いの自然性比較として扱う。

### 10.3 個人・非公開前提

声質R&Dは完全個人・非公開・非配布・非商用の範囲で進めてよい。ただし、外部公開する可能性が出た場合だけ、許諾済み音声またはオリジナル声へ切り替える。

守るルール:

- 生成音声、学習済み音声モデル、学習データセットを公開・配布・販売しない。
- SNS、動画、配信、外部アプリなど第三者が聴ける場所で使用しない。
- 素材入手元の規約に反する取得・利用をしない。
- DRMや技術的保護手段を回避して素材化しない。
- 音声素材をクラウドTTS/STT/学習サービスへ投入しない。
- 本人発言と誤認させる利用をしない。

## 11. STT/音声入力

| 技術 | 位置づけ | 向いていること | 注意 |
|:---|:---|:---|:---|
| Web Speech API | MVP | 実装最速。UIからマイク入力を扱いやすい。 | ブラウザ/OS依存。Chrome系ではクラウド認識の場合あり。 |
| whisper.cpp | ローカル第一候補 | Windows、CPU/CUDA、モデルサイズ選択。日本語精度とローカル性のバランスが良い。 | リアルタイムにはVAD/チャンク制御が必要。CUDAはVRAM競合。 |
| Moonshine | 低遅延比較 | 音声エージェント向け低遅延。話している途中の更新UIに向く。 | 日本語精度とWindows運用は実測。 |
| Vosk | 軽量比較 | オフライン、ストリーミング、低負荷、常時待受やコマンド入力向き。 | Whisper系より自然文認識精度は落ちる可能性。 |

## 12. Phase 4: Integration

Phase 4では、Phase 1〜3で作った実証パーツを1つのWindowsアプリ/システムとして統合する。

優先順位:

1. `localhost` で統合成功。
2. LAN/Tailscale IPでアクセス。
3. 必要ならHTTPS/PWA。

HTTPS:

- Tailscale Serve + MagicDNS + HTTPS は推奨だが必須ではない。
- mkcertも開発用/代替として残す。
- スマホマイクやPWAでHTTPSが必要になった時点で対応する。

プロセス管理:

- `yachiyo_supervisor.py` を作る。
- `start_yachiyo.bat` はsupervisor起動用wrapperにする。
- Ollama / Backend / TTS / Frontendを起動・監視する。
- health checkとログ分離を行う。
- 共有GPUメモリ使用やVRAM逼迫を検出したら軽量modeへ落とす。

## 13. 改訂後アーキテクチャ

```text
Frontend (Vite/React/R3F)
  - Chat UI
  - VRM Avatar
  - AudioQueue
  - SpeechProvider
  - Thinking/Status Panel
  - Settings
        |
        | WebSocket / HTTP(S)
        v
Backend (FastAPI)
  - Conversation Orchestrator
  - Ollama Adapter
  - Tool Router + HitL
  - Memory Hub
  - Control Planner
  - Audio Chunker
        |
        +--> Ollama: Qwen3-VL 8B
        +--> Memory DB: LanceDB / SQLite fallback
        +--> Embedding: Qwen3-Embedding / MiniLM fallback
        +--> TTS Gateway: Style-Bert-VITS2 / GPT-SoVITS / F5-TTS / IndexTTS2 / fallback
        +--> STT Gateway: Web Speech / whisper.cpp / Moonshine / Vosk
        +--> Search: Web search + Playwright/SearXNG option
```

## 14. 新マイルストーン

### Milestone 0: 技術ベンチ

目的: RTX3060実機で選定を確定する。

完了条件:

- `qwen3-vl:8b` の日本語会話、画像理解、ツール/JSON、速度を検証。
- `num_ctx` 8k/16k/32k のVRAM・tokens/sec記録。
- Qwen3-Embedding-0.6B と MiniLM の日本語記憶検索比較。
- LanceDB / SQLite系 / ChromaDB の軽さ・速度比較。
- localhost/LAN/Tailscale IPでアクセス確認。HTTPSは必要時に追加。

### Milestone 1: Text Agent MVP

完了条件:

- WebSocketチャットが動く。
- Qwen3-VLで日本語ペルソナ応答ができる。
- Ollama tool callingで安全な読み取りツールが動く。
- 危険ツールはHitL承認が必須。
- SQLiteに会話・イベント・監査ログが残る。

### Milestone 2: Memory MVP

完了条件:

- append-only memory schemaを実装。
- ユーザーの好み・事実を抽出。
- 忘却スコアで通常RAG対象を制御。
- 「何を覚えてる？」「忘れて」が動く。
- keyword + vector fusion または LanceDB hybrid retrieval が動く。

### Milestone 3: Avatar MVP

完了条件:

- VRM表示。
- `emotion_trigger` で表情が変わる。
- `motion_trigger` で簡易モーション。
- 思考/状態パネルが表示できる。
- モバイルで最低20〜30fpsを維持。

### Milestone 4: Voice MVP

完了条件:

- 仮TTS/fallback TTSで音声再生。
- AudioQueueでチャンク再生。
- RMSリップシンク。
- TTS OFFモード。
- Web Speech APIで音声入力。

### Milestone 5: Local Voice

完了条件:

- ローカルSTT providerの1つを実装。
- whisper.cpp / Moonshine / Vosk のうち少なくとも1つをWindowsで実測。
- 必要に応じてスマホ音声入力のHTTPS要件を検証。

### Milestone 6: Voice R&D

完了条件:

- GPT-SoVITSの少量参照/few-shot品質ゲート。
- GPT-SoVITSで満足できない場合のStyle-Bert-VITS2学習データ品質ゲート。
- 完全個人・非公開・外部投入禁止の運用ルール確認。
- GPT-SoVITS / F5-TTS / IndexTTS2 の比較評価。
- LLM + TTS同居時のVRAM実測。

### Milestone 7: System Integration

完了条件:

- `yachiyo_supervisor.py` で4プロセス起動。
- runtime mode切替。
- ログ分離とhealth check。
- localhostで統合動作。
- LAN/Tailscale IPでアクセス。
- 必要ならHTTPS/PWA。

## 15. 既存計画書への反映項目

### `project.md`

- 完全ローカル無料の意味を再定義する。
- GPUをRTX3060 専用VRAM12GB + 共有GPUメモリ8GBと明記する。
- LLMをQwen3-VL 8B一本化に変更する。
- ChromaDB固定をやめ、LanceDB第一候補にする。
- XML制御をControlPlanner JSONイベントへ変更する。
- リモートアクセスはまず動作優先にする。

### `phase1_core_agent/PLAN.md`

- `llama3:8b` 固定をやめる。
- Qwen3-VL 8Bをメインモデルとして採用し、LLM-jp-4等は将来必要時のみ再検討にする。
- `stream_parser.py` の責務を縮小またはlegacy化する。
- `tool_router.py`, `control_planner.py`, `audit_log.py`, `model_profiles.py`, `memory_store.py` を追加する。
- 記憶schemaをappend-only + 忘却スコアに変更する。

### `phase2_avatar_ui/PLAN.md`

- `SpeechProvider` 抽象化を追加する。
- 思考/状態パネルを追加する。
- expression mapとmotion presetを外部設定化する。
- XMLタグを直接解釈しない方針にする。

### `phase3_voice_tts/PLAN.md`

- GPT-SoVITSを第一検証TTSにする。
- GPT-SoVITSで満足できない場合のみStyle-Bert-VITS2へ移行する。
- F5-TTS / IndexTTS2 / VOICEVOXをR&D比較枠に残す。
- `TTSGateway` 抽象化を追加する。
- RTX3060専用VRAM12GBで同居実測を必須にする。

### `phase4_integration/PLAN.md`

- HTTPS/PWAは後段対応へ変更する。
- `yachiyo_supervisor.py` を追加する。
- runtime modeを導入する。
- 専用VRAM12GB基準で統合する。

## 16. 採用判断

すぐ採用:

- Qwen3-VL 8B一本化。
- XMLタグ方式を主設計から外す。
- Ollama tool calling / structured outputs。
- LanceDB第一候補。
- TTSGateway化。
- SpeechProvider化。
- localhost/LAN/Tailscale IPで統合動作を優先。

実測後に採用:

- LanceDB vs SQLite + sqlite-vector/sqlite-vec vs ChromaDB。
- Qwen3-Embedding-0.6B vs MiniLM。
- whisper.cpp vs Moonshine vs Vosk。
- WebGPU renderer。
- GPT-SoVITS / F5-TTS / IndexTTS2。

採用しない:

- 実在声優の声質再現を本体MVPの成功条件にする。
- LLM出力XMLだけでツール実行する。
- 破壊的操作をLLM判断だけで実行する。
- Funnel等で外部公開する。
- 共有GPUメモリ8GBを性能予算として使う。
- 初期実装で複数LLMを同時運用する。

## 17. 参照ソース

- Qwen3 official blog: https://qwenlm.github.io/blog/qwen3/
- Qwen3 8B model card: https://huggingface.co/Qwen/Qwen3-8B
- Qwen3-VL Ollama library: https://ollama.com/library/qwen3-vl
- Qwen3 Embedding official blog: https://qwenlm.github.io/blog/qwen3-embedding/
- Ollama Qwen3 library: https://ollama.com/library/qwen3
- Ollama context length docs: https://docs.ollama.com/context-length
- Ollama tool calling docs: https://docs.ollama.com/capabilities/tool-calling
- Ollama structured outputs: https://registry.ollama.com/blog/structured-outputs
- Ollama embeddings docs: https://docs.ollama.com/capabilities/embeddings
- ELYZA models: https://huggingface.co/elyza
- rinna models: https://huggingface.co/rinna
- LLM-jp-4 8B Instruct model card: https://huggingface.co/llm-jp/llm-jp-4-8b-instruct
- LLM-jp-4 8B Q4_K_M GGUF: https://huggingface.co/mosh-hf/llm-jp-4-8b-instruct-GGUF
- LLM-jp release: https://llm-jp.nii.ac.jp/en/news/release-of-llm-jp-3-1-series-instruct4/
- Gemma 3 Hugging Face blog: https://huggingface.co/blog/gemma3
- Microsoft Phi-4 announcement: https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-phi-4-microsoft%E2%80%99s-newest-small-language-model-specializing-in-comple/4357090
- LanceDB docs: https://docs.lancedb.com/
- LanceDB embedded OSS: https://www.lancedb.com/lp/embedded-oss
- sqlite-vector README: https://github.com/sqliteai/sqlite-vector
- SQLite-vec Mozilla Builders: https://builders.mozilla.org/project/sqlite-vec/
- ChromaDB docs: https://docs.trychroma.com/
- Qdrant hybrid queries: https://qdrant.tech/documentation/concepts/hybrid-queries/
- three-vrm GitHub: https://github.com/pixiv/three-vrm
- Three.js WebGPURenderer docs: https://threejs.org/docs/pages/WebGPURenderer.html
- Style-Bert-VITS2 GitHub: https://github.com/litagin02/Style-Bert-VITS2
- GPT-SoVITS GitHub: https://github.com/RVC-Boss/GPT-SoVITS
- GPT-SoVITS API v2: https://github.com/RVC-Boss/GPT-SoVITS/blob/main/api_v2.py
- F5-TTS GitHub: https://github.com/SWivid/F5-TTS
- IndexTTS2 paper: https://huggingface.co/papers/2506.21619
- whisper.cpp GitHub: https://github.com/ggml-org/whisper.cpp
- Moonshine GitHub: https://github.com/moonshine-ai/moonshine
- Vosk GitHub: https://github.com/alphacep/vosk-api
- MDN Web Speech API: https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API
- SearXNG docs: https://docs.searxng.org/
- Tailscale Serve docs: https://tailscale.com/docs/features/tailscale-serve
- Tailscale HTTPS docs: https://tailscale.com/docs/how-to/set-up-https-certificates
- Japanese Copyright Act Article 30: https://www.japaneselawtranslation.go.jp/ja/laws/view/3379
- Agency for Cultural Affairs AI and Copyright: https://www.bunka.go.jp/seisaku/chosakuken/aiandcopyright.html
