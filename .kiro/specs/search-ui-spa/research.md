# Research & Design Decisions

## Summary
- **Feature**: `search-ui-spa`
- **Discovery Scope**: Extension（既存Search APIに対するフロントエンドUI追加）
- **Key Findings**:
  - 既存Search APIは `POST /api/artworks/search` でFastAPI上に構築済み。CORSやStaticFilesの設定は未実装
  - Searchサービスは`uvicorn`でポート8000で起動。Dockerfileに静的ファイルコピーを追加すれば同一コンテナから配信可能
  - フレームワーク不要の軽量SPA（Vanilla JS + fetch API）で要件を満たせる

## Research Log

### FastAPI静的ファイル配信
- **Context**: SPAをSearchサービスと同一コンテナで配信する方法
- **Sources Consulted**: FastAPI公式ドキュメント、既存`app.py`コード
- **Findings**:
  - `fastapi.staticfiles.StaticFiles`でマウント可能
  - `app.mount("/", StaticFiles(directory="static", html=True))` でSPA配信
  - APIエンドポイントはprefix `/api/` で競合しない
  - `html=True`を指定すると`index.html`を自動配信
- **Implications**: Dockerfileに`COPY`行追加とapp.pyに`mount`追加のみで統合可能

### APIレスポンス構造
- **Context**: UIが消費するデータ型の確認
- **Sources Consulted**: `shared/models/search.py`
- **Findings**:
  - `SearchRequest`: `query` (str, 1-500), `limit` (int, 1-100, default=24)
  - `SearchResponse`: `parsed_query` (ParsedQuery), `items` (list[SearchResultItem])
  - `SearchResultItem`: `artwork_id`, `title`, `artist_name`, `thumbnail_url`, `score`, `match_reasons`
  - `ParsedQuery`: `semantic_query`, `filters` (QueryFilters), `boosts` (QueryBoosts)
  - `QueryFilters`: `motif_tags` (list[str]), `color_tags` (list[str])
- **Implications**: UIはこれらの型をそのまま消費。追加APIは不要

### CORS設定
- **Context**: SPAがAPIを呼び出すためのCORS要件
- **Sources Consulted**: FastAPI CORSMiddleware
- **Findings**:
  - 同一オリジン配信（StaticFiles + API同一サーバー）であればCORS不要
  - 開発時にViteなど別サーバーを使う場合のみCORSが必要
  - 同一コンテナ配信を選択すればCORS設定不要
- **Implications**: 静的ファイルをSearchサービスからマウントすることでCORS問題を回避

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Vanilla JS SPA | ビルドツール不要のHTML/CSS/JS | 依存ゼロ、軽量、即時デプロイ可能 | 大規模化に不向き | 簡易UIとしては最適。要件7に合致 |
| React/Vue SPA | フレームワークベースSPA | コンポーネント再利用、型安全 | ビルドインフラ必要、オーバーエンジニアリング | 要件7の「フレームワーク依存を最小限」に反する |
| HTMX + Jinja2 | サーバーサイドレンダリング | Pythonテンプレート統合 | 非SPA、ページ遷移発生 | 要件7.3に反する |

## Design Decisions

### Decision: Vanilla JS SPA
- **Context**: 簡易検索UIに最適な技術選択
- **Alternatives Considered**:
  1. React SPA — コンポーネント再利用可能だがビルドインフラ必要
  2. Vue SPA — 軽量だがビルドツール依存
  3. Vanilla JS — ビルドツール不要、静的ファイルのみ
- **Selected Approach**: Vanilla JS（HTML + CSS + JS、ビルドツール不要）
- **Rationale**: 要件7「フレームワーク依存を最小限にした静的ファイル」に直接対応。検索UIの規模ではフレームワークの恩恵が少ない
- **Trade-offs**: コンポーネント再利用性は低いが、単一画面のSPAでは問題にならない
- **Follow-up**: UIの複雑性が増す場合はフレームワーク導入を検討

### Decision: SearchサービスからのStaticFiles配信
- **Context**: SPAファイルのホスティング方法
- **Alternatives Considered**:
  1. 別コンテナ（nginx等） — インフラ追加が必要
  2. SearchサービスのStaticFilesマウント — 既存インフラで完結
- **Selected Approach**: FastAPI StaticFilesマウントでSearchサービスから配信
- **Rationale**: 追加コンテナ不要、CORS不要、Dockerfile変更のみで統合可能
- **Trade-offs**: Searchサービスの責務が増えるが、静的ファイル配信は軽量
- **Follow-up**: 静的ファイルのパスがAPIルートと競合しないことを確認

## Risks & Mitigations
- サムネイル画像がFirebase Storage URLを直接参照 — CORS許可がFirebase側で必要な可能性あり。ただし既にpublic URLとして提供されている前提
- Vanilla JSでの状態管理が複雑化するリスク — 検索→表示の単純フローのため低リスク
- ブラウザキャッシュによる静的ファイル更新遅延 — クエリパラメータによるキャッシュバスト

## References
- [FastAPI StaticFiles](https://fastapi.tiangolo.com/tutorial/static-files/) — 静的ファイル配信の公式ドキュメント
- [CSS Grid Layout](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_grid_layout) — レスポンシブグリッドの実装パターン
