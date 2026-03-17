# Technology Stack

## Architecture

オフライン/オンライン分離アーキテクチャ。重い推論処理（VLM・埋め込み生成）はオフラインバッチで実行し、オンライン検索はQdrantへの軽量クエリに限定する。

- **Offline**: Firebase Storage → 前処理 → VLM推論 → 埋め込み生成 → Qdrant保存
- **Online**: クエリ分解 → payloadフィルタ + ベクトル検索 → リランキング → レスポンス

## Core Technologies

- **Language**: Python（MLパイプライン・API共通）
- **Vector DB**: Qdrant（named vectors + payload filtering）
- **VLM**: Qwen2.5-VL（キャプション・タグ抽出、オフライン）
- **Embedding**: SigLIP2（image_semantic / text_semantic ベクトル生成）
- **Storage**: Firebase Storage（画像原本）
- **Container**: Docker Compose（ローカル開発・デプロイ）

## Key Libraries

- Qdrant Python client — ベクトルDB操作
- Transformers / MLX — モデル推論（Appleシリコン最適化）
- FastAPI or similar — Search API / Internal API サービング
- Pillow / OpenCV — 画像前処理・色抽出

## Development Standards

### コード品質
- Python 3.11+、型ヒント必須
- ruff / black によるフォーマット統一

### テスト
- pytest、モデル推論はモックで単体テスト
- 検索精度はオフライン評価セットで検証

## Development Environment

### Required Tools
- Docker / Docker Compose
- Appleシリコン Mac（MLX対応）
- Python 3.11+

### Common Commands
```bash
# 起動: docker compose up -d
# インジェスション: docker compose exec ingestion python -m ingestion.run
# テスト: pytest
```

## Key Technical Decisions

| 決定事項 | 選択 | 理由 |
|----------|------|------|
| 主ベクトル | SigLIP2のみ（DINOv2なし） | 実装の軽さ優先、多言語image-text検索向き |
| 色検索 | payloadフィルタ | ベクトルより厳密条件に強い |
| ムード検索 | ベクトル類似度 | タグ固定では表現が死ぬ |
| リランキング | アプリ側スコア合成 | v1ではデバッグしやすさ優先 |
| VLM出力保存 | 正規化後のみ | 語彙揺れ吸収のためTaxonomy Mapper必須 |

---
_Document standards and patterns, not every dependency_
