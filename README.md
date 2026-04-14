# image-search-local

Firebase Storage上のアートワーク画像を、日本語の自然言語で検索するローカル画像検索システム。

「やさしい感じで、緑と金が入っていて、空っぽい作品」のような直感的なクエリで、雰囲気・色・モチーフを組み合わせた検索ができる。


## 概要

オフラインでの特徴抽出パイプライン（インジェスション）と、オンラインのセマンティック検索APIを分離した構成。Appleシリコンのローカル環境で完結する。

- VLM（Qwen2.5-VL等）によるキャプション・タグ自動生成
- SigLIP2による画像/テキストの埋め込みベクトル生成（1152次元）
- Qdrantのpayloadフィルタ + ベクトル類似度検索
- 日本語クエリの自動分解（色・モチーフ・明るさ・ムード）
- ヒット理由の説明付き検索結果
- freeform_keywords による Taxonomy 外モチーフの保持・検索活用
- ブラウザから操作できる検索UI（SPA）


## アーキテクチャ

MLモデル推論はホスト側（LM Studio + SigLIP2埋め込みサービス）で実行し、アプリケーションロジックとデータストアはDocker Compose内で管理するハイブリッド構成。

```
ホスト側:
  LM Studio (VLM)           -- ポート 1234
  SigLIP2 Embedding Service -- ポート 8100

Docker Compose:
  Qdrant                    -- ポート 6333
  Ingestion Service         -- バッチ実行
  Search Service            -- ポート 8000
```


## 必要な環境

- macOS (Appleシリコン)
- Docker / Docker Compose
- Python 3.11以上
- LM Studio（Vision対応モデル）


## セットアップ

### 1. Python環境

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

SigLIP2埋め込みサービスを動かす場合は追加で:

```bash
pip install torch transformers
```

### 2. 環境変数

```bash
cp .env.example .env
```

`.env` を編集し、Firebase Storage のバケット名を設定する。Firebase認証情報は `config/firebase-credentials.json` に配置する。

### 3. Qdrant起動

```bash
docker compose up -d qdrant
```

### 3.5. エイリアス初期化（Search Service 起動前に 1 回だけ）

検索サービスは起動時にエイリアス（既定 `artworks_current`）の存在を検証し、未定義なら CRITICAL ログを出して起動に失敗する。初回セットアップ時は以下で既存コレクション（`QDRANT_COLLECTION` が指す `artworks_v1`）にエイリアスを張る。

```bash
docker compose run --rm ingestion python -m services.ingestion.reindex init-alias
```

ログに `event=reindex.alias.initialized` が出れば成功。既に存在する場合は `reindex.alias.init_skipped` で no-op。

### 4. SigLIP2埋め込みサービス起動

```bash
uvicorn services.embedding.app:app --host 0.0.0.0 --port 8100
```

初回起動時にモデル（約3.5GB）をダウンロードする。ウォームアップ完了まで20-30秒程度かかる。

バックグラウンドで起動する場合:

```bash
nohup uvicorn services.embedding.app:app --host 0.0.0.0 --port 8100 > /tmp/siglip2.log 2>&1 &
```

停止する場合:

```bash
kill $(lsof -i :8100 -t)
```

### 5. LM Studio

LM StudioでVision対応モデル（Qwen2.5-VL、Qwen3.5等）をロードし、サーバーをポート1234で起動する。

構造化出力（response_format: json_schema）に対応したモデルを推奨する。

### 6. Search Service起動

```bash
uvicorn services.search.app:app --host 0.0.0.0 --port 8000
```

または Docker Compose で起動する場合:

```bash
docker compose up -d search
```


## 使い方

### 検索UI（ブラウザ）

Search Service 起動後、ブラウザで http://localhost:8000/ にアクセスする。

- 自然言語クエリを入力して検索ボタンまたはEnterで実行
- 結果はサムネイル付きグリッドで表示（レスポンシブ対応）
- 各カードにヒット理由バッジを表示、ホバーでスコア詳細
- クエリ解析結果（抽出されたモチーフ・色フィルタ）を可視化

### 検索API

```bash
curl -X POST http://localhost:8000/api/artworks/search \
  -H "Content-Type: application/json" \
  -d '{"query": "穏やかな青い空と海のある絵", "limit": 10}'
```

レスポンス例:

```json
{
  "parsed_query": {
    "semantic_query": "穏やかな青い空と海のある絵",
    "filters": {
      "motif_tags": ["sky", "sea"],
      "color_tags": ["blue"]
    },
    "boosts": {
      "brightness_min": null
    }
  },
  "items": [
    {
      "artwork_id": "art-001",
      "title": "Ocean View",
      "artist_name": "Artist A",
      "thumbnail_url": "https://...",
      "score": 0.87,
      "match_reasons": ["雰囲気が近い", "skyモチーフ一致", "blue色一致"]
    }
  ]
}
```

### 個別作品登録API

```bash
curl -X POST http://localhost:8000/internal/artworks/index \
  -H "Content-Type: application/json" \
  -d '{
    "artwork_id": "art-001",
    "image_url": "https://example.com/art-001.jpg",
    "title": "Ocean View",
    "artist_name": "Artist A"
  }'
```

### バッチインジェスション

```bash
docker compose run --rm ingestion python -m services.ingestion.run
```

Firebase Storageの `FIREBASE_STORAGE_PREFIX` で指定したフォルダから未処理画像を取得し、特徴抽出パイプラインを実行してQdrantに保存する。既にインデックス済みの画像はスキップされる。

## 無停止再インデックス (Blue/Green)

タグ体系刷新・埋め込みモデル更新などで全件再インデックスが必要な場合、検索サービスを停止せずに新しい物理コレクションへ切り替えられる。CLI は `services/ingestion/reindex.py` に集約されている。

**詳細な運用手順は [docs/runbooks/reindex.md](docs/runbooks/reindex.md) を参照** (各シナリオに前提条件・期待ログ・失敗時アクション・チェックリストを掲載)。主要サブコマンド:

```bash
# 新物理コレクションを作成し切替まで実行
docker compose run --rm ingestion python -m services.ingestion.reindex run \
    --target-version v2 [--force-recreate] [--dry-run] [--skip-validation] [--sample-ratio 0.9]

# 再インデックス期間中に旧コレクションへ入った差分を新コレクションへ複製
docker compose run --rm ingestion python -m services.ingestion.reindex catchup \
    --source artworks_v1 --target artworks_v2

# エイリアスを旧バージョンへ戻す
docker compose run --rm ingestion python -m services.ingestion.reindex rollback --to v1

# 物理コレクションを削除 (現行ターゲットは拒否)
docker compose run --rm ingestion python -m services.ingestion.reindex drop-collection artworks_v0
```

切替は Qdrant エイリアスをアトミックに更新するため、検索リクエストは停止せず新コレクションへルーティングされる。検証失敗時は切替を行わず、旧コレクションが稼働を継続する。


## プロジェクト構成

```
services/
  ingestion/           インジェスションサービス
    pipeline.py          パイプライン統括（VLM+埋め込み+色抽出の並列実行）
    image_preprocessor.py  画像正規化・サムネイル生成
    color_extractor.py     支配色・brightness/saturation/warmth抽出
    firebase_storage.py    Firebase Storage連携
    batch.py               バッチ処理ログ管理
    run.py                 バッチ実行エントリポイント
  search/              検索サービス
    app.py               FastAPI アプリケーション + 検索UI配信
    query_parser.py      日本語クエリ分解（色・モチーフ・明るさ）
    reranker.py          スコア合成リランキング（freeform_keywords含む）
    static/              検索UI（SPA）
      index.html           エントリポイント
      css/style.css        レスポンシブレイアウト
      js/                  Vanilla JSモジュール群
  embedding/           SigLIP2埋め込みサービス（ホスト側）
    app.py               FastAPI アプリケーション
    encoder.py           SigLIP2モデルラッパー
shared/
  clients/             外部サービスクライアント
    vlm.py               LM Studio VLMクライアント
    embedding.py         SigLIP2埋め込みクライアント
  models/              Pydanticデータモデル
  qdrant/              Qdrant CRUD・検索
    repository.py        コレクション管理・upsert・検索
  taxonomy/            語彙正規化
    mapper.py            VLM出力の同義語変換・ストップワード除去・freeform_keywords収集
    definitions.json     辞書データ（motif_vocabulary 約815語）
tests/                 テスト（252件）
```


## 検索の仕組み

### クエリ分解

日本語クエリを以下の要素に自動分解する:

- 色: 緑 -> green, 金 -> gold, 青 -> blue 等（14色対応）
- モチーフ: 空 -> sky, 海 -> sea, 花 -> flower, 城 -> castle, 猫 -> cat 等（Met Museum 812タグ全対応）
- 明るさ: 「明るい」-> brightness_min=0.6, 「暗い」-> brightness_min=0.0
- ムード: クエリ全体をSigLIP2テキスト埋め込みに渡す（多言語対応を活用）

### スコア合成

```
最終スコア = 0.65 * ベクトル類似度
           + 0.15 * モチーフ一致度
           + 0.10 * 色一致度
           + 0.05 * 明るさ近接度
           + 0.05 * freeform_keywords一致度
```

### インジェスションパイプライン

画像ごとに以下を実行する:

1. 画像前処理（RGB統一・サムネイル生成）
2. VLM推論 + 画像埋め込み + 色抽出（並列実行）
3. Taxonomy正規化（同義語変換・ストップワード除去・freeform_keywords収集）
4. テキスト埋め込み生成（キャプション確定後に逐次実行）
5. Qdrant upsert（freeform_keywordsインデックス含む）


## テスト

```bash
# 単体テスト + 統合テスト（外部サービス不要）
pytest tests/ --ignore=tests/test_e2e.py

# E2Eテスト（LM Studio + SigLIP2 + Qdrant 稼働時のみ）
pytest tests/test_e2e.py -v
```


## 環境変数一覧

| 変数名 | 既定値 | 説明 |
|--------|--------|------|
| QDRANT_HOST | localhost | Qdrantホスト |
| QDRANT_PORT | 6333 | Qdrantポート |
| QDRANT_COLLECTION | artworks_v1 | コレクション名 |
| LM_STUDIO_URL | http://localhost:1234 | LM Studioエンドポイント |
| EMBEDDING_SERVICE_URL | http://localhost:8100 | SigLIP2サービスエンドポイント |
| FIREBASE_CREDENTIALS_PATH | | Firebase認証情報JSONパス |
| FIREBASE_STORAGE_BUCKET | | Firebase Storageバケット名 |
| FIREBASE_STORAGE_PREFIX | | バッチ取得対象のフォルダプレフィックス |
| VECTOR_DIM | 1152 | 埋め込みベクトル次元数 |


## ライセンス

Private
