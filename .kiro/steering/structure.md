# Project Structure

## Organization Philosophy

サービス分離型のモノレポ構成。オフライン処理（Ingestion）とオンライン処理（Search）を独立サービスとして分け、共通ロジック（モデル・Qdrantクライアント・Taxonomy）は共有モジュールに配置する。

## Directory Patterns

### サービスディレクトリ
**Location**: `/services/<service-name>/`
**Purpose**: 各サービスの実装コード
**Example**: `/services/ingestion/`, `/services/search/`

### 共有モジュール
**Location**: `/shared/`
**Purpose**: サービス間で共有するロジック（モデルラッパー、DB接続、Taxonomy定義）
**Example**: `/shared/models/`, `/shared/qdrant/`, `/shared/taxonomy/`

### 設定・定義
**Location**: `/config/`
**Purpose**: Docker Compose定義、環境設定、Qdrantスキーマ定義
**Example**: `docker-compose.yml`, `/config/qdrant/`, `.env.example`

### ドキュメント
**Location**: `/docs/`
**Purpose**: 設計ドキュメント、リサーチメモ
**Example**: `docs/research.md`, `docs/plan.md`

### 仕様
**Location**: `.kiro/specs/`, `.kiro/steering/`
**Purpose**: Spec駆動開発の仕様管理・プロジェクトステアリング

## Naming Conventions

- **ディレクトリ**: snake_case（`query_parser/`, `color_extractor/`）
- **Pythonファイル**: snake_case（`taxonomy_mapper.py`）
- **クラス**: PascalCase（`QueryParser`, `TaxonomyMapper`）
- **関数・変数**: snake_case（`extract_colors()`, `mood_tags`）
- **定数**: UPPER_SNAKE_CASE（`DEFAULT_LIMIT`, `VECTOR_DIM`）

## Import Organization

```python
# 1. 標準ライブラリ
import json
from pathlib import Path

# 2. サードパーティ
from qdrant_client import QdrantClient
from fastapi import FastAPI

# 3. 共有モジュール（プロジェクト内）
from shared.models.siglip import SigLIPEncoder
from shared.taxonomy import TaxonomyMapper

# 4. ローカル（同サービス内）
from .pipeline import IngestionPipeline
```

## Code Organization Principles

- **サービス独立性**: 各サービスは独立してコンテナ化・起動可能
- **共有の明示**: サービス間共有は必ず`/shared/`を経由、直接importしない
- **設定外部化**: 環境変数またはconfig fileで設定を注入、ハードコードしない
- **Taxonomy集中管理**: タグの正規化ルールは`/shared/taxonomy/`に一元管理

---
_Document patterns, not file trees. New files following patterns shouldn't require updates_
