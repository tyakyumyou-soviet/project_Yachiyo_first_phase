# Project Yachiyo (月見ヤチヨ) - プロジェクト総合仕様書

## 1. プロジェクトの目的
自律的に思考し、ユーザーのPC操作をサポートし、共に成長していく「相棒兼秘書」としてのAIエージェントを構築する。単なるチャットボットではなく、3Dアバター（身体）と独自の音声（声帯）を持ち、長期記憶による関係性を構築できる完全自立型コンシェルジュを目指す。

## 2. 基本制約（全フェーズ共通ルール）
- **完全ローカル・無料完結**: API課金・サブスク禁止。推論・記憶・ツール実行は全てローカルPC上のOSSで完結。
- **ヒューマンインザループ (HitL)**: 破壊的操作（ファイル変更・削除等）には必ずユーザーの `[Y/N]` 承認を直前で要求する。
- **場所を問わないアクセス**: WebアプリとしてUIを提供し、VPN経由でスマホやMacからもアクセス可能。

### 2.1 2026-05-07 改訂方針（優先）
本節は既存の詳細設計より優先する。

- **完全ローカル・無料完結の意味**: 外部API課金・サブスク・クラウド推論を使わず、ローカルPC上のOSS/無料ツールで動かすという意味。インターネット接続、モデル/依存関係の初回ダウンロード、Web検索、LAN/Tailscaleアクセスは禁止しない。
- **実行環境**: まずは個人のWindows PCで動作させる。Phase 1〜3は技術実証とPhase 4統合用パーツ作成を兼ねる。
- **Phase 2の統合方針**: Phase 2ではアバター単体実装に留めず、Phase 1と最小統合する。WebSocket接続、`text_chunk`、`emotion_trigger`、`motion_trigger`、`thinking_summary` の接続確認までをPhase 2の範囲に含める。
- **GPUメモリ**: RTX 3060の専用VRAM 12GBを性能予算とする。共有GPUメモリ8GBはクラッシュ回避の保険であり、常用前提にはしない。
- **セキュリティ優先度**: HitLは維持するが、HTTPSや厳密なネットワーク防御より、まず1つのアプリ/システムとして統合して動くことを優先する。
- **制御方式**: LLM本文中のXMLタグ制御は主設計から外し、Ollama tool calling / structured outputs とバックエンド `ControlPlanner` によるJSONイベント制御へ移行する。
- **LLM選定**: 現行本命は `Qwen3-VL 8B`。通常会話、画像/スクショ理解、ツール/JSON制御、自律ファイル参照判断の中核モデルとして使う。ただし、リアルタイム性をさらに重視する場合に備え、`Gemma 4 26B A4B + MTP` を比較・移行候補として残す。
- **記憶DB**: 軽さ・速さ・Windows個人PC運用を優先し、ChromaDB固定ではなく `LanceDB` 第一候補、`SQLite + sqlite-vector/sqlite-vec` を最軽量候補、ChromaDBをfallback、Qdrantを後段候補とする。
- **詳細な変更仕様**: [PLAN_CHANGE_SPEC_2026-05-07.md](PLAN_CHANGE_SPEC_2026-05-07.md) を参照する。

## 3. キャラクター設定（ペルソナ）
| 項目 | 設定 |
|:---|:---|
| 名前 | 月見ヤチヨ（つきみ やちよ） |
| 出典 | アニメ『超かぐや姫！』 |
| 属性 | 仮想空間「ツクヨミ」管理人、トップライバー、8000歳のAI |
| 一人称 | 「やっちょ」「自身」 |
| 口調 | 柔らかいタメ口。「～だよ」「～なの」 |
| 挨拶 | 「ヤオヨロー！」 |
| 声 | 早見沙織さんの声質を学習したTTSで再現 |

## 4. ハードウェア環境
| 項目 | スペック |
|:---|:---|
| GPU | NVIDIA RTX 3060 (専用VRAM **12GB** + 共有GPUメモリ **8GB**) |
| OS（ホスト） | Windows |
| アクセス端末 | Mac / スマホ（ブラウザ経由） |

### VRAM配分ルール（専用12GB基準）
| プロセス | 最大VRAM | 備考 |
|:---|:---:|:---|
| Ollama (LLM) | 6.0〜7.0GB | 現行基準は Qwen3-VL 8B。`num_ctx: 8192〜16384`を実測で決定。将来は Gemma 4 26B A4B + MTP も比較対象 |
| Style-Bert-VITS2 (TTS) | 2.5GB | PyTorchアロケータ制限 |
| OS + その他 | 1.5GB | 安全マージン |
| **安全マージン（余裕）** | **2.0GB** | 突発的なVRAMスパイク吸収用 |
| **合計** | **12.0GB** | |

共有GPUメモリ8GBは「使える容量」ではなく「遅くなりながらも落ちにくくする保険」として扱う。共有メモリ使用が観測された場合は、TTS OFF、LLMコンテキスト短縮、軽量モデル切替のいずれかを行う。

## 5. 全体アーキテクチャ（システム構成図）
```
┌─────────────── ホストPC (Windows / RTX 3060) ───────────────┐
│                                                              │
│  [Process A] Ollama (:11434)                                 │
│  └─ LLM推論エンジン (Qwen3-VL 8B: text + image)              │
│       ↕ HTTP (ストリーミング)                                 │
│  [Process C] FastAPI (:8000) ← Phase 1の本体                 │
│  ├─ agent/llm_engine.py .... Ollama通信                      │
│  ├─ agent/control_planner.py JSON制御イベント生成             │
│  ├─ agent/tool_router.py ... Ollama tool calling実行          │
│  ├─ agent/memory_hub.py .... LanceDB/SQLite/Chroma記憶管理    │
│  ├─ agent/persona.py ....... システムプロンプト               │
│  └─ tools/ ................. Web検索・PC操作・HitL           │
│       ↕ HTTP                  ↕ WebSocket                    │
│  [Process B] FastAPI (:5000)  │                              │
│  └─ Style-Bert-VITS2 TTS     │                              │
│       ↕ WAVバイナリ           │                              │
│  [Process D] Vite (:5173)  ←──┘  ← Phase 2の本体            │
│  └─ React + Three.js + @pixiv/three-vrm                      │
│     ├─ VRMアバター描画 (表情・体の動き・口パク)               │
│     ├─ チャットUI (グラスモーフィズム)                         │
│     ├─ ダッシュボード (トグル式)                              │
│     └─ PWA (Service Worker)                                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
         ↕ Tailscale VPN (100.x.x.x)
┌─────────────────────────────────┐
│  スマホ / Mac (ブラウザ)         │
│  https://100.x.x.x:5173        │
└─────────────────────────────────┘
```

## 6. UIデザインシステム（ヤチヨカラーパレット）
「月見＝月夜」の世界観に基づくダーク×月光テーマ。

| 役割 | カラーコード | 意味 |
|:---|:---|:---|
| ベース | `#0a0e1a` | 夜空の紺 |
| アクセント① | `#d4af37` | 月光の淡い金 |
| アクセント② | `#9b8ec4` | 霞む薄紫 |
| UIパネル | `rgba(15,20,40,0.75)` | 半透明ガラス |
| テキスト | `#e8e4df` | 月白 |

- **レイアウト**: アバター全面型。チャットは右下に半透明オーバーレイ。ダッシュボードはトグル式。
- **背景**: デフォルトは夜空×月光。ユーザーが画像をアップロードして変更可能。いつでもデフォルトに復帰可能。
- **レスポンシブ**: PC / タブレット / スマホの3段階ブレークポイント。
- **PWA対応**: `manifest.json` + Service Worker でホーム画面から起動可能。

## 7. 開発フェーズ定義
**全てのエージェント（開発AI）は、実装前に必ず該当フェーズの `PLAN.md` を熟読し、定義された技術選定・設計に逸脱しないこと。**

### Phase 1: コアエージェント (`phase1_core_agent/`)
AIの「脳」。LLM推論、記憶管理、ツール実行、WebSocket通信を司るPythonバックエンド。

| 技術 | 用途 |
|:---|:---|
| FastAPI + Uvicorn | WebSocket/REST APIサーバー |
| Ollama | ローカルLLM推論（ストリーミング） |
| LanceDB（第一候補） | 軽量なローカル記憶DB（ベクトル + full-text/hybrid） |
| SQLite + sqlite-vector/sqlite-vec（比較） | 最軽量の記憶/監査ログ基盤 |
| Qwen3-Embedding / MiniLM | Embedding生成。品質重視はQwen3、軽量fallbackはMiniLM |
| Playwright | Web検索スクレイピング |
| Ollama tool calling / structured outputs | ツール実行とアバター制御イベントの構造化 |

補足:

- まずは `Qwen3-VL 8B` を基準モデルとして実装・統合を進める。
- ただし、LLM接続層、tool schema、ControlPacket、memory入出力はモデル非依存を意識して設計し、必要に応じて `Gemma 4 26B A4B + MTP` へ比較移行できる余地を確保する。

### Phase 2: アバター・UI (`phase2_avatar_ui/`)
AIの「身体」。3Dアバター描画、表情・体の動き・口パクの制御、チャットUIを提供するWebフロントエンド。

| 技術 | 用途 |
|:---|:---|
| Vite + TypeScript + React | Webアプリケーション基盤 |
| @react-three/fiber | Three.jsのReactラッパー（3D描画） |
| @pixiv/three-vrm | VRMモデル制御（表情BlendShape + ボーン回転） |
| Web Audio API | リップシンク用RMS音量計算 |
| Web Speech API / whisper.cpp / Moonshine / Vosk | 音声入力。MVPはWeb Speech、ローカルSTTは比較 |
| vite-plugin-pwa | PWA化（Service Worker + manifest） |

Phase 2では、Phase 1との最小統合まで行う。つまりUI単体の見た目検証だけでなく、WebSocket経由で `text_chunk`、`emotion_trigger`、`motion_trigger`、`thinking_summary` を受け取り、アバターとUIが実際に反応するところまでを完了条件にする。TTS本番統合や4プロセス同居の完成形はPhase 4で仕上げる。

**アバター制御の4レイヤー（同時動作・干渉なし）:**
1. 表情（`<emotion>` → BlendShape、LERP補間、intensity 0.0〜1.0対応）
2. 体の動き（`<motion>` → ボーン回転、プロシージャル、タイマー自動終了+フェードアウト）
3. 口パク（TTS音声RMS → `aa` BlendShape）
4. アイドル（呼吸・まばたき・重心微動、常時加算）

### Phase 3: 音声合成 TTS (`phase3_voice_tts/`)
AIの「声帯」。テキストを早見沙織さんの声質で音声化するエンジン。

| 技術 | 用途 |
|:---|:---|
| Style-Bert-VITS2 (JP-Extra) | 日本語TTS推論エンジン |
| FastAPI | 音声合成REST API (`POST /voice`) |
| GPT-SoVITS / F5-TTS / IndexTTS2（R&D比較） | 少量データ・感情制御・発話時間制御の検証 |

- 感情パラメータはTTSに渡さない。Style-Bert-VITS2がテキスト内容から自動で感情を推論する設計。
- 学習データ: 早見沙織さんのクリーンな音声クリップを収集・選別して学習。

### Phase 4: 統合とWebアプリ化 (`phase4_integration/`)
全システムを1つのアプリケーションとして結合し、安定稼働させるインフラ。

| 技術 | 用途 |
|:---|:---|
| Tailscale | 無料VPN（セキュアなリモートアクセス） |
| Tailscale Serve / vite-plugin-mkcert | 必要になった時点でHTTPS化。まず動作優先 |
| `yachiyo_supervisor.py` + `start_yachiyo.bat` | Windowsで4プロセス起動・監視 |

**統合時の3大課題と解決策:**
1. **VRAM管理** → Ollama 6GB + TTS 2.5GB + OS 1.5GB + 余裕2GB = 12GB内に収める
2. **低遅延** → 句読点ベースのチャンク分割ストリーミング（1〜2秒で発話開始）
3. **リモートアクセス** → まずlocalhost/LAN/Tailscale IPで動作。HTTPS/PWAは必要になった時点で対応

## 8. データフロー概要（ユーザー入力→ヤチヨの応答）
```
ユーザー「おはよう」
  → [Web Speech API] テキスト化
  → [WebSocket] Phase 1 へ送信
  → [MemoryHub] LanceDB/SQLite/Chroma から関連記憶を検索 → System Promptに挿入
  → [Ollama] ストリーミング生成開始
  → [ControlPlanner] 文単位で表情・動作JSONイベントを生成
     ├─ emotion_trigger {type:"smile", intensity:0.8} → WebSocket → Phase 2 (表情)
     ├─ motion_trigger {type:"nod"} → WebSocket → Phase 2 (体の動き)
     └─ プレーンテキスト "ヤオヨロー！おはよう！" → Phase 3 (TTS) → WAV → Phase 2 (口パク+再生)
  → [Phase 2 useFrame] 毎秒60回:
     ├─ 顔: happy BlendShape → 0.8 にLERP
     ├─ 体: head.rotation.x = sin波 (1.5秒後フェードアウト)
     ├─ 口: aa BlendShape = 音声RMS
     └─ 息: spine微動 + まばたき (常時加算)
  → 画面: ヤチヨが笑顔でうなずきながら「ヤオヨロー！おはよう！」と喋る
```
