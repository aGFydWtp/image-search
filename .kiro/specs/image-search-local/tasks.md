# Implementation Plan

- [ ] 1. プロジェクト基盤とDocker Compose環境構築
- [x] 1.1 Pythonプロジェクトの初期化とディレクトリ構造の作成
  - モノレポ構造（services/ingestion, services/search, shared）の作成
  - pyproject.tomlまたはrequirements.txtで依存パッケージを定義（fastapi, qdrant-client, pillow, firebase-admin, httpx, pydantic）
  - .env.exampleにQdrant接続先、LM StudioエンドポイントURL、SigLIP2サービスURL、Firebase認証情報パスを定義
  - 共有データモデル（ArtworkPayload, SearchRequest, SearchResponse等）をsharedモジュールに配置
  - _Requirements: 6.1, 6.2_

- [x] 1.2 Docker Compose定義とQdrantコンテナの構築
  - docker-compose.ymlにQdrant（arm64ネイティブイメージ）、Ingestion Service、Search Serviceの各コンテナを定義
  - Qdrantデータ用のnamed volumeで永続化を設定
  - コンテナからホスト側MLサービスへの接続設定（host.docker.internal経由）
  - 各サービスのDockerfile作成（Python 3.11+ slim base）
  - ヘルスチェック設定（Qdrantの起動待ち）
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 1.3 QdrantRepositoryの実装とコレクション初期化
  - artworks_v1コレクションの作成（image_semantic: 1152d Cosine, text_semantic: 1152d Cosine のnamed vectors定義）
  - payload indexの作成（mood_tags, motif_tags, color_tags: KeywordIndex, brightness_score: FloatIndex）
  - artwork pointのupsert機能（named vectors + payload）
  - artwork_idによる存在確認機能
  - prefilter + vector searchの実行機能（payloadフィルタ条件構築 + ベクトル類似度検索の組み合わせ）
  - ensure_collection()による初回起動時の自動セットアップ
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Contracts: QdrantRepository Service_

- [ ] 2. ホスト側MLサービス連携クライアントの実装
- [x] 2.1 (P) VLMClientの実装（LM Studio連携）
  - LM StudioのOpenAI互換chat/completions APIを呼び出すHTTPクライアントを実装
  - 画像をbase64エンコードしてvisionメッセージとして送信
  - メタデータ抽出用プロンプトの定義（caption, motif候補, style候補, subject候補, mood候補をJSON形式で出力させる）
  - レスポンスJSONの解析とVLMExtractionResult型へのバリデーション
  - JSON解析失敗時のリトライとフォールバック処理
  - _Requirements: 1.2_
  - _Contracts: VLMClient Service_

- [x] 2.2 (P) EmbeddingClientの実装（SigLIP2サービス連携）
  - ホスト側SigLIP2埋め込みサービスのREST APIを呼び出すHTTPクライアントを実装
  - 画像バイナリから1152次元のimage_semanticベクトルを取得する機能
  - テキスト文字列から1152次元のtext_semanticベクトルを取得する機能
  - 接続失敗時の適切なエラーハンドリング
  - _Requirements: 1.5, 3.3_
  - _Contracts: EmbeddingClient Service_

- [ ] 2.3 (P) SigLIP2埋め込みサービスのスタンドアロン実装
  - ホスト側で動作するFastAPIベースの埋め込みサービスを作成
  - SigLIP2 SO400M-patch14-384モデルをTransformers + MPSバックエンドでロード
  - POST /embed/image（画像バイナリ → 1152dベクトル）エンドポイント
  - POST /embed/text（テキスト → 1152dベクトル）エンドポイント
  - GET /health ヘルスチェックエンドポイント
  - モデルの初回ロードとウォームアップ処理
  - _Requirements: 1.5, 3.3_

- [ ] 3. 画像前処理とTaxonomy管理の実装
- [ ] 3.1 (P) ImagePreprocessorの実装
  - 画像バイナリの正規化処理（リサイズ、色空間統一）
  - サムネイル画像の生成（固定サイズ）
  - 画像メタデータ（width, height, aspect_ratio）の抽出
  - 対応フォーマット: JPEG, PNG, WebP
  - _Requirements: 1.1_
  - _Contracts: ImagePreprocessor Service_

- [ ] 3.2 (P) ColorExtractorの実装
  - 画像から支配色を抽出し、正規化された英語色名タグ（green, gold, blue等）に変換
  - パレットHEXコード（上位3-5色）の抽出
  - brightness_score（0.0-1.0）の算出
  - saturation_score（0.0-1.0）の算出
  - warmth_score（0.0-1.0）の算出
  - k-meansクラスタリングまたはヒストグラム分析による色抽出
  - _Requirements: 1.3_
  - _Contracts: ColorExtractor Service_

- [ ] 3.3 (P) TaxonomyMapperの実装
  - モチーフ正規化辞書の定義と、VLM出力のモチーフ候補を正規化済みタグに変換する機能
  - ムード語彙セットの定義と、ムード候補を統制語彙にマッピングする機能
  - スタイル・サブジェクトタグの正規化ルール
  - 不要・冗長タグの除去フィルタリング
  - taxonomy_version（v1）の付与
  - 辞書データはYAMLまたはJSON形式で管理し、更新が容易な構成
  - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - _Contracts: TaxonomyMapper Service_

- [ ] 4. インジェスションパイプラインの実装
- [ ] 4.1 Firebase Storage連携とバッチ処理基盤
  - firebase-admin SDKを使用したFirebase Storage接続の初期化
  - 未処理画像の一覧取得機能（処理済み管理はQdrant内のartwork_id存在確認で判定）
  - 画像のダウンロード機能（バイナリ取得）
  - バッチ処理の開始・終了・処理件数・エラー件数のログ記録（構造化JSON形式）
  - コマンドライン実行エントリポイント（`python -m ingestion.run`）
  - _Requirements: 1.1, 1.7, 8.3_

- [ ] 4.2 インジェスションパイプライン統合
  - 画像取得→前処理→VLM推論＋色抽出（並列）→Taxonomy正規化→埋め込み生成→Qdrant保存の一連のパイプラインを統合
  - VLM推論と画像埋め込み生成の並列実行（asyncioまたはconcurrent.futures）
  - テキスト埋め込みはキャプション確定後に逐次実行
  - 各ステップのエラーハンドリング: VLM失敗時は該当作品スキップ、SigLIP2失敗時はエラーキュー記録
  - Qdrantへのupsert（新規作成・既存更新の両対応）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.1, 8.4_
  - _Contracts: IngestionService Service, Batch_

- [ ] 5. クエリパーサーと検索サービスの実装
- [ ] 5.1 QueryParserの実装
  - 自然言語クエリからムード表現を抽出しsemantic_queryに設定する機能（ルールベース＋辞書）
  - 日本語色名（緑、金、青、赤等）を英語正規化形（green, gold, blue, red等）のcolor_tagsフィルタ値に変換
  - モチーフ表現（空、海、花、山等）をmotif_tagsフィルタ値に変換
  - 明るさ関連表現（明るい、暗い等）からbrightness_scoreの下限値をboostsに設定
  - 分解結果をParsedQuery型（semantic_query, filters, boosts）で出力
  - 分解不能な場合はsemantic_query=元クエリ、空filtersで返却
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Contracts: QueryParser Service_

- [ ] 5.2 Rerankerの実装
  - ベクトル類似度スコアとpayloadメタデータを組み合わせたスコア合成（vector_similarity 70%, motif_match 15%, color_match 10%, brightness_affinity 5%）
  - motif_matchスコア: クエリのmotif_tagsと結果のmotif_tagsの一致度算出
  - color_matchスコア: クエリのcolor_tagsと結果のcolor_tagsの一致度算出
  - brightness_affinityスコア: クエリのbrightness boostと結果のbrightness_scoreの近接度
  - match_reasons生成: ヒット要因を自然言語リスト（「やさしい雰囲気が近い」「空モチーフ一致」等）で構成
  - _Requirements: 3.4, 3.5_
  - _Contracts: Reranker Service_

- [ ] 5.3 SearchServiceとAPIエンドポイントの実装
  - POST /api/artworks/search エンドポイントの実装（query: str, limit: int = 24）
  - クエリ分解→payloadフィルタ構築→テキスト埋め込み生成→Qdrant prefilter + vector search→リランキング→レスポンス構築の統合
  - フィルタ構築とテキスト埋め込み生成の並列実行
  - SearchResponse型でparsed_queryとitemsを返却
  - Qdrant接続失敗時のHTTP 503レスポンス
  - 空クエリのHTTP 400バリデーション
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 8.2_
  - _Contracts: SearchService Service, API_

- [ ] 6. 個別登録APIの実装
- [ ] 6.1 POST /internal/artworks/index エンドポイントの実装
  - artwork_id, image_url, title, artist_nameを受け取りインジェスションパイプラインを単一作品に対して実行
  - Qdrant内にartwork_idが既に存在する場合は既存pointを更新（upsert）
  - 画像URL取得失敗時のエラーログ記録と適切なHTTPエラーレスポンス（404または502）
  - IndexRequest / IndexResponse のPydanticモデルによるバリデーション
  - _Requirements: 5.1, 5.2, 5.3_
  - _Contracts: IngestionService API_

- [ ] 7. 結合テストとE2Eテスト
- [ ] 7.1 ユニットテストの実装
  - QueryParser: 各種日本語クエリ（ムード、色、モチーフ、複合、分解不能）に対する分解結果の検証
  - TaxonomyMapper: VLM出力の正規化ルール（モチーフ、ムード、除去）の検証
  - ColorExtractor: 色抽出・brightness/saturation算出の精度検証
  - Reranker: スコア合成ロジックとmatch_reasons生成の検証
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 7.1, 7.2, 7.3, 1.3, 3.4, 3.5_

- [ ] 7.2 統合テストの実装
  - IngestionService: モックVLM/EmbeddingClient経由でパイプライン全体フロー（取得→前処理→VLM→色抽出→Taxonomy→埋め込み→保存）の動作確認
  - SearchService: モックQdrant経由で検索フロー全体（クエリ分解→フィルタ→ベクトル検索→リランキング→レスポンス）の動作確認
  - QdrantRepository: テスト用Qdrantコンテナでのupsert/search/exists動作確認
  - APIエンドポイント: FastAPI TestClientを使用した /api/artworks/search と /internal/artworks/index のリクエスト/レスポンス検証
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.1, 5.2, 5.3_

- [ ]* 7.3 E2Eテストの実装
  - テスト用画像セットを使用したインジェスション→検索の一気通貫テスト
  - 検索精度評価: 評価クエリセットに対するrecall@k測定
  - ホスト側MLサービス（LM Studio + SigLIP2）が起動している環境でのみ実行可能
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
