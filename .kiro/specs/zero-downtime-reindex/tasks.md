# Implementation Plan

> 各タスクは TDD（Red → Green → Refactor）で進める。サブタスクに「tests ...」を先に列挙し、その後に「impl ...」を配置する。`(P)` マーカーは互いに独立して並行実装可能なことを示す。

## 1. Settings / Config 拡張

- [x] 1.1 `Settings` に新フィールドを追加
  - tests: `tests/test_config.py` に `qdrant_alias`/`qdrant_api_key`/`reindex_validation_ratio`/`reindex_sample_queries_path`/`log_format`/`log_level`/`service_name`/`env_name` の既定値と env 上書き挙動を検証するケースを追加
  - impl: `shared/config.py:Settings` に上記フィールドを追記、`qdrant_api_key` は `SecretStr` または `str | None` で扱う
  - impl: `.env.example` を更新
  - _Requirements: 1.4, 4.1, 7.6, 8.1, 8.2_

## 2. 構造化ログ基盤 (StructuredLogger)

- [x] 2.1 Cloud Logging 互換 JSON フォーマッタを実装 (P)
  - tests: `tests/test_structured_logger.py` を新設し以下を検証
    - `severity` が `DEBUG/INFO/NOTICE/WARNING/ERROR/CRITICAL` に正しくマップされる
    - `logging.googleapis.com/labels` に `service`/`env`/`event` が含まれる
    - `logging.googleapis.com/trace` / `spanId` が `X-Cloud-Trace-Context` から抽出される
    - 既知シークレットキー（`qdrant_api_key` 等）が `***` に置換される
    - 例外を含むレコードが `@type=...ReportedErrorEvent` で出力される
    - `log_format=text` でフォールバック出力になる
  - impl: `shared/logging/structured.py`（新設）に `JsonFormatter` と `configure_logging(settings)` を実装
  - _Requirements: 7.3, 7.4, 7.5, 7.6, 8.2_

- [x] 2.2 各サービスエントリポイントでロガー初期化
  - tests: サービス起動時に `configure_logging` が 1 度だけ呼ばれることを `tests/test_search_app.py` / `tests/test_batch_runner.py` に追加
  - impl: `services/search/app.py` lifespan 冒頭、`services/ingestion/run.py` と新規 `reindex.py` の先頭で `configure_logging(settings)` を呼ぶ
  - _Requirements: 7.3, 7.6_

## 3. CollectionResolver / AliasAdmin (shared/qdrant)

- [x] 3.1 `CollectionResolver` を実装 (P)
  - tests: `tests/test_collection_resolver.py` を新設
    - `resolve()` が `get_collection_aliases` の戻り値から現在ターゲットを返す
    - エイリアス未定義時は `AliasNotFoundError` を送出
    - 連続呼び出しでキャッシュせず毎回クライアントに問い合わせる
  - impl: `shared/qdrant/resolver.py`（新設）、例外型 `AliasNotFoundError` を定義
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 3.2 `AliasAdmin` を実装 (P)
  - tests: `tests/test_alias_admin.py` を新設
    - `swap(alias, new_target)` が `DeleteAlias`+`CreateAlias` を **単一** `update_collection_aliases` で発行
    - `new_target` 不在で `CollectionNotFoundError`
    - `current_target()` が現在ターゲットを返す／未定義で None
    - `drop_physical_collection(name, alias)` が現行ターゲットに対して失敗する
    - `rollback` は `swap` の薄いラッパとして機能する
    - 失敗時に `event=reindex.alias.swap.failed` でログ出力
  - impl: `shared/qdrant/alias_admin.py`（新設）、`SwapResult` dataclass を含む
  - _Requirements: 3.1, 3.2, 3.3, 5.1, 5.2, 5.3, 5.4_

## 4. QdrantRepository 改修

- [x] 4.1 Repository をエイリアス解決対応に変更
  - tests: 既存 `tests/test_qdrant_repository.py` を改修
    - 読み取り (`search`/`exists`/`count`) が毎回 Resolver を経由する
    - 書き込み (`upsert_artwork`) は `target_collection=None` で Resolver 経由、明示指定でその物理名に書く
    - `ensure_collection(physical_name)` が引数の物理名でコレクションを作成する
    - `count(physical_name=None)` が新設され、物理名指定／Resolver 経由の両方で動作する
  - impl: `shared/qdrant/repository.py`
    - コンストラクタを `(client, resolver, vector_dim)` に変更
    - `self._collection` を撤去し、Read は `resolver.resolve()`、Write は引数優先
    - `ensure_collection` を `physical_name: str` 引数化
    - `count` メソッド新設
  - _Requirements: 1.1, 1.3, 2.4, 6.1, 6.2_

- [x] 4.2 Repository のファクトリ関数を追加 (P)
  - tests: `tests/test_qdrant_factory.py` を新設し、Settings から `Resolver`+`Repository` を生成できることを検証
  - impl: `shared/qdrant/factory.py`（新設）に `build_repository(settings) -> tuple[QdrantClient, CollectionResolver, QdrantRepository]` を用意
  - _Requirements: 1.1, 8.1_

## 5. 検索サービス配線

- [x] 5.1 lifespan を新 API に合わせて書き換え
  - tests: `tests/test_e2e.py` / `tests/test_integration.py` を更新し、エイリアスが存在しない状態で起動した場合にエラー終了することを検証（`AliasNotFoundError`）
  - impl: `services/search/app.py` の lifespan で `shared/qdrant/factory.build_repository` を使い、`CollectionResolver.exists()` チェックを追加
  - _Requirements: 1.1, 1.2_

- [x] 5.2 `/healthz` と `/readyz` を実装
  - tests: `tests/test_search_app.py` に追加
    - `/healthz` は依存不問で 200 `{"status":"ok"}`
    - `/readyz` は Resolver が解決できかつ count 成功時に 200 `{"alias","collection","points_count"}`
    - エイリアス削除シナリオで `/readyz` が 503
    - `points_count` 等にシークレットが含まれないこと（`qdrant_api_key` がレスポンスに出ない）
  - impl: `services/search/app.py` に 2 エンドポイントを追加、`/health` は `/readyz` に委譲
  - _Requirements: 7.1, 8.5, 8.2_

## 6. ValidationGate

- [x] 6.1 検証ロジックを実装 (P)
  - tests: `tests/test_validation_gate.py` を新設
    - 件数比 >= 閾値で passed=True
    - 件数比 < 閾値で passed=False かつ詳細 `check.name='point_count_ratio'`
    - サンプル検索が例外で passed=False
    - サンプル検索 0 件は passed 側（例外でない限り OK）
    - `skip_validation=True` で合格扱いかつ `event=reindex.validation.skipped` を WARN で出力
  - impl: `shared/qdrant/validation.py`（新設）`ValidationGate`, `ValidationReport`, `CheckResult`
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 6.2 サンプルクエリ定義と読み込み (P)
  - tests: `tests/test_reindex_samples.py` を新設
    - 正常 JSON を読める
    - 不正 JSON／ファイル不在は `SampleQueriesError` を送出
  - impl: `config/reindex_samples.json` のひな形、`shared/qdrant/sample_queries.py`（新設）でロード & embedding 呼び出し
  - _Requirements: 4.2, 4.3_

## 7. ReindexOrchestrator と CLI

- [x] 7.1 `ReindexOrchestrator` を実装
  - tests: `tests/test_reindex_orchestrator.py` を新設
    - 新コレクション作成 → 投入 → 検証 → swap の順に呼ぶ
    - 既存同名コレクションに対して既定では `CollectionExistsError`、`force_recreate=True` で削除再作成
    - 投入途中で例外 → swap 呼ばれない、新コレクションは残る
    - 検証失敗 → swap 呼ばれない、非ゼロ終了を示す値を返す
    - `dry_run=True` → Validator は呼ぶが swap は呼ばない
    - 進捗ログ `reindex.progress` が一定件数ごとに出力される
    - 既存 point_id ハッシュ方式で**冪等**に再実行可能
  - impl: `services/ingestion/reindex.py`（新設）に `ReindexOrchestrator`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1-4.4, 7.2_

- [ ] 7.2 CLI エントリポイントを実装
  - tests: `tests/test_reindex_cli.py` を新設
    - `reindex run --target-version v2` が Orchestrator を呼び、成功で exit 0、失敗で非ゼロ
    - `--dry-run`/`--skip-validation`/`--force-recreate`/`--sample-ratio` の各フラグが伝搬
    - `rollback --to vN-1` が `AliasAdmin.rollback` を呼ぶ
    - `drop-collection <name>` が現行ターゲットに対して失敗する
    - `--target-version` の正規表現バリデーション（`^[a-zA-Z0-9_-]+$`）
  - impl: `services/ingestion/reindex.py` に `python -m services.ingestion.reindex` のエントリ (argparse)
  - _Requirements: 2.1, 2.2, 3.4, 5.2, 5.3, 5.4_

## 8. 差分インジェスション側の整合

- [ ] 8.1 差分 upsert が現行エイリアス対象に書き込む
  - tests: `tests/test_batch_runner.py` / `tests/test_integration.py` に追加
    - 差分 ingestion が `upsert_artwork(target_collection=None)` を使い Resolver 経由になる
    - 指定物理名とエイリアス先が不一致の場合 `event=ingestion.alias.mismatch` の WARN が 1 回出る
  - impl: `services/ingestion/run.py` / `batch.py` / `pipeline.py` の呼び出し箇所を Resolver 経由に切替
  - _Requirements: 6.1, 6.2, 6.4_

- [ ] 8.2 キャッチアップ投入手順の検証
  - tests: `tests/test_reindex_catchup.py` を新設し、再インデックス中に入った差分が `reindex run --catchup` 相当の再実行で新コレクションにも反映されることを検証
  - impl: Orchestrator に `catchup=True` モードを追加（`artwork_id` 一覧を旧コレクションから取得 → 新コレクションへ upsert）
  - _Requirements: 6.3_

## 9. Docker / 起動スクリプト整備

- [ ] 9.1 docker-compose と README を alias 前提へ
  - impl: `docker-compose.yml` に `QDRANT_ALIAS` 等を受け渡し、初回起動用のワンショットジョブ `reindex init-alias` の利用を README に記載
  - impl: `reindex init-alias` サブコマンドを追加（`artworks_<version>` 未指定時は既定 `artworks_v1` を対象にエイリアス作成）
  - _Requirements: 1.2, 1.4_

## 10. 運用 Runbook（人間 / LLM 共通参照）

- [ ] 10.1 `docs/runbooks/reindex.md` を作成
  - impl: 固定 H2 見出し（新規再インデックス / ドライラン / ロールバック / 旧コレクション削除 / ヘルス確認 / 障害判断）をこの順序で用意
  - impl: 各 H2 配下に `### 前提条件` / `### コマンド` / `### 期待ログ` / `### 成功判定` / `### 失敗時アクション` を **必ず同順序** で配置
  - impl: コマンドは ```` ```bash ```` コードブロック、イベントキーは ```` ```text ```` コードブロック内に 1 行 1 キーで記載
  - impl: 各シナリオ末尾に `### 成功判定チェックリスト` (チェックボックス形式) を入れる
  - _Requirements: 9.1, 9.2, 9.3, 9.5_

- [ ] 10.2 エントリドキュメントから Runbook を発見可能にする
  - impl: `CLAUDE.md` に `## Operational Runbooks` セクションを追加し `docs/runbooks/reindex.md` への相対リンクを記載
  - impl: `README.md` の運用セクションから同ファイルへのリンクを追加
  - _Requirements: 9.4_

- [ ] 10.3 PR テンプレートで Runbook 同期を強制
  - impl: `.github/pull_request_template.md` を作成／更新し、「CLI 引数・design.md を変更した場合は `docs/runbooks/reindex.md` を更新した」チェック項目を追加
  - _Requirements: 9.6_

## 11. 統合テスト（Qdrant 実コンテナ）

- [ ] 11.1 Blue/Green 切替の E2E
  - tests: `tests/test_reindex_e2e.py` を新設
    - コレクション A 作成 → alias → A に upsert → 検索
    - コレクション B 作成 → B に upsert → validate pass → swap
    - 切替前後で検索結果が期待通り（B の内容）に変わる
    - swap 直前直後の連続検索で 500 が発生しない
    - `rollback --to A` で検索結果が A に戻る
    - 現行ターゲット A を `drop-collection` しようとして失敗する
  - _Requirements: 3.1-3.3, 5.1-5.4, 6.1_

- [ ] 11.2 `/readyz` 連動の運用シナリオ
  - tests: `tests/test_reindex_e2e.py` に追加
    - エイリアスを意図的に削除 → `/readyz` 503、再作成 → 200
  - _Requirements: 7.1, 8.5_

## 12. ドキュメント最終反映

- [ ] 12.1 README の運用章を更新
  - impl: 初回カットオーバー手順（停止許容）、日常の再インデックス手順、Runbook へのリンクを追加
  - _Requirements: 9.4_

- [ ] 12.2 design.md / Runbook の整合チェック（セルフレビュー）
  - impl: design.md のイベントキー一覧と Runbook の `期待ログ` が 1 対 1 で一致することを確認
  - _Requirements: 9.6_
