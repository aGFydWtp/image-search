# Research & Design Decisions

---
**Purpose**: image-search-local フィーチャーの技術調査記録
---

## Summary
- **Feature**: `image-search-local`
- **Discovery Scope**: New Feature（グリーンフィールド）
- **Key Findings**:
  - Docker内からApple Metal GPUにアクセス不可 → MLモデルはホスト側で実行しAPI経由で利用
  - SigLIP2はLM Studio非対応（エンコーダモデル） → Transformers+MPSで専用埋め込みサービスが必要
  - Qwen2.5-VL-7BはLM Studioで対応可能（OpenAI互換API経由）
  - Qdrant arm64 Docker imageはネイティブ対応済み

## Research Log

### Docker内GPU/MLXアクセス制限
- **Context**: Appleシリコン上のDocker Composeで全サービスを動かす設計の妥当性検証
- **Sources**: Docker公式ブログ、Chariot Solutions技術記事
- **Findings**:
  - Docker DesktopはApple Metal GPUパススルーに非対応
  - Docker Model Runner（2026 GA）はvLLM-metalバックエンドで一部対応するが、SigLIP2のようなエンコーダモデルは対象外
  - PodmanのVulkan-to-Metal layerも限定的
- **Implications**: MLモデル推論はホスト側で実行し、Docker内のサービスはHTTP APIで呼び出す設計とする

### SigLIP2モデル選定
- **Context**: 画像・テキスト埋め込み生成のモデル選定
- **Sources**: HuggingFace Model Hub、mlx-community
- **Findings**:
  - SigLIP2バリエーション: Base(768d), Large(1024d), SO400M(1152d), Giant-opt(1536d)
  - SO400M-patch14-384が最も人気（ダウンロード数最多）
  - MLXポートは8-bit Base版のみ（実用に不向き）
  - Transformers+MPSでM-series Macで快適に動作（SO400M: ~1Bパラメータ）
  - LM Studioはエンコーダモデルに非対応 → 生成モデル専用
- **Implications**: SigLIP2はホスト側でPython + Transformers + MPSのスタンドアロン埋め込みサービスとして稼働。ベクトル次元は1152（SO400M）

### Qwen2.5-VLモデル選定
- **Context**: キャプション・タグ抽出用VLMの選定
- **Sources**: HuggingFace Model Hub、mlx-vlm、LM Studio対応状況
- **Findings**:
  - 利用可能サイズ: 3B, 7B, 32B, 72B
  - MLX完全対応: 全サイズで複数量子化バリエーションあり
  - 7B-Instruct-4bit: 16GB+ Macで最適なバランス
  - LM Studio対応: GGUF/MLX形式で利用可能、OpenAI互換API提供
- **Implications**: LM Studioで7B-4bitをホスト。Ingestion ServiceからOpenAI互換APIでキャプション・タグ生成を呼び出す

### Qdrant Python Client API
- **Context**: named vectors、payload indexing、filtered searchのAPI設計
- **Sources**: Qdrant公式ドキュメント、Python Client API Reference
- **Findings**:
  - `create_collection()`: vectors_configにdict形式でnamed vectors定義
  - `create_payload_index()`: KeywordIndexParamsでタグ配列のインデックス作成
  - `search_points()`: query_filterとquery_vectorを組み合わせてprefilter+ベクトル検索
  - `upsert()`: PointStructのvectorをdict形式で複数named vectors指定
  - Qdrant v1.11+ arm64ネイティブDocker image提供
- **Implications**: API設計は安定しており、設計通りの実装が可能

### FastAPI + Firebase Admin SDK
- **Context**: API サービングフレームワークとFirebase Storage接続
- **Sources**: FastAPI公式ドキュメント、Firebase Admin Python SDK
- **Findings**:
  - FastAPI 0.135.1: Pydantic v2必須、response_model自動バリデーション
  - firebase-admin SDK: `storage.bucket().list_blobs()` でファイル一覧取得
- **Implications**: 標準的な構成で問題なし

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 全Docker内包型 | モデル含め全てDocker内 | 環境統一 | Apple Metal GPU不可、実現不能 | 却下 |
| ハイブリッド型（採用） | MLモデル=ホスト、その他=Docker | GPU活用可、コンテナ軽量 | ホスト依存あり | LM Studio + 埋め込みサービス |
| 全ホスト型 | Docker不使用 | 最もシンプル | 環境再現性低、Qdrant管理手間 | v1には過剰にシンプル |

## Design Decisions

### Decision: MLモデル実行のホスト/Docker分離
- **Context**: Appleシリコン上でMLモデル推論をDocker内で実行できない
- **Alternatives Considered**:
  1. Docker内でCPU推論 — 極端に遅い
  2. Docker Model Runner — SigLIP2非対応
  3. ホスト側実行 + API公開（採用）
- **Selected Approach**: Qwen2.5-VLはLM Studio（OpenAI互換API）、SigLIP2はホスト側Python+MPSで埋め込みサービスを提供
- **Rationale**: GPU活用でき、既にLM Studioインストール済み、コンテナは軽量に保てる
- **Trade-offs**: ホスト環境依存が増える。CI/CDではモック必要
- **Follow-up**: SigLIP2埋め込みサービスのAPI設計を確定する

### Decision: SigLIP2 SO400Mモデル選択
- **Context**: 埋め込みベクトルのモデルとサイズ選定
- **Alternatives Considered**:
  1. Base (768d) — 軽量だが精度劣る
  2. SO400M (1152d) — バランス良好（採用）
  3. Giant-opt (1536d) — 高精度だがメモリ重い
- **Selected Approach**: `google/siglip2-so400m-patch14-384`（1152次元）
- **Rationale**: 最もダウンロード数が多く、~1Bパラメータで16GB Macでも快適
- **Trade-offs**: Giant-optより精度は劣るが、v1には十分
- **Follow-up**: 実際の検索精度を評価セットで検証

### Decision: ベクトル次元数 1152
- **Context**: SigLIP2 SO400Mの出力次元
- **Selected Approach**: image_semantic=1152, text_semantic=1152（同一モデル系列）
- **Rationale**: research.mdの768からSO400M選定により1152に更新

## Risks & Mitigations
- **LM Studio API安定性**: OpenAI互換APIに依存 → フォールバックとしてTransformers直接呼び出しの設計余地を残す
- **SigLIP2埋め込みサービス単一障害点**: ホスト側プロセス障害 → ヘルスチェック＋自動再起動（systemdまたはlaunchd）
- **Qdrantデータ永続化**: Docker volume喪失 → バックアップ戦略（v2で検討）
- **VLM出力品質のばらつき**: Qwen2.5-VL 7B 4bitの量子化による精度劣化 → Taxonomy Mapperで吸収

## References
- [Qdrant ARM Architecture Support](https://qdrant.tech/blog/qdrant-supports-arm-architecture/)
- [Qdrant Payload Indexing](https://qdrant.tech/documentation/concepts/indexing/)
- [Qdrant Filtered Search](https://qdrant.tech/articles/vector-search-filtering/)
- [SigLIP2 SO400M on HuggingFace](https://huggingface.co/google/siglip2-so400m-patch14-384)
- [Qwen2.5-VL on HuggingFace](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)
- [Docker Metal GPU制限](https://chariotsolutions.com/blog/post/apple-silicon-gpus-docker-and-ollama-pick-two/)
- [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices)
- [Firebase Admin SDK Storage](https://firebase.google.com/docs/storage/admin/start)
