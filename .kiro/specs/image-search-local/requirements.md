# Requirements Document

## Introduction
Firebase Storage上の画像を、雰囲気・色・モチーフなどの自然言語キーワードで検索可能にするローカル画像検索システムの要件定義。Appleシリコン上でSigLIP2およびQwen2.5-VLの軽量モデルを活用し、Qdrantベクトルデータベースによるオフラインインジェスションとオンラインセマンティック検索を実現する。Docker Composeで構築し、将来的にk8sへの移行にも対応可能な設計とする。

## Requirements

### Requirement 1: オフライン画像インジェスション
**Objective:** As a システム管理者, I want Firebase Storageの画像を自動的に取得し特徴抽出・ベクトル化してQdrantに保存したい, so that オンライン検索時に高速なセマンティック検索が可能になる

#### Acceptance Criteria
1. When インジェスションパイプラインが実行された時, the Ingestion Service shall Firebase Storageから未処理の画像を取得し、前処理（画像正規化・サムネイル生成）を実行する
2. When 画像の前処理が完了した時, the Ingestion Service shall Qwen2.5-VLを用いてキャプション生成、モチーフ候補抽出、スタイル・サブジェクト候補抽出をJSON形式で出力する
3. When 画像の前処理が完了した時, the Ingestion Service shall 支配色抽出、brightness/saturationスコア算出、カラータグ正規化を実行する
4. When VLMおよびカラー抽出が完了した時, the Ingestion Service shall Taxonomy Mapperを通じてモチーフ正規化、ムード語彙マッピング、不要タグ除去を実行する
5. When タクソノミーマッピングが完了した時, the Ingestion Service shall SigLIP2を用いてimage_semanticベクトルとtext_semanticベクトルを生成する
6. When 全ての特徴抽出が完了した時, the Ingestion Service shall Qdrantのartworks_v1コレクションに、named vectors（image_semantic, text_semantic）とpayloadを1 pointとして保存する
7. The Ingestion Service shall 1日1回以上の定期実行に対応する

### Requirement 2: Qdrantデータスキーマ管理
**Objective:** As a 開発者, I want 作品データを構造化されたスキーマでQdrantに保存したい, so that 柔軟なフィルタリングとベクトル検索を組み合わせた検索が実現できる

#### Acceptance Criteria
1. The Qdrant Collection shall artworks_v1コレクションにimage_semantic（Cosine距離）とtext_semantic（Cosine距離）の2つのnamed vectorsを定義する
2. The Qdrant Collection shall 各pointのpayloadに以下の必須フィールドを含む: artwork_id, title, artist_name, image_url, thumbnail_url, caption, mood_tags, motif_tags, color_tags, brightness_score, saturation_score
3. Where 追加メタデータが利用可能な場合, the Qdrant Collection shall style_tags, palette_hex, is_abstract, has_character, year, medium, width, height, aspect_ratioをpayloadに含める
4. The Qdrant Collection shall payload内のmotif_tags, color_tags, mood_tagsに対してフィルタリングインデックスを有効化する

### Requirement 3: オンライン検索API
**Objective:** As a エンドユーザー, I want 自然言語で画像を検索したい, so that 「やさしい感じで、緑と金が入っていて、空っぽい作品」のような直感的なクエリで作品を見つけられる

#### Acceptance Criteria
1. When ユーザーが検索クエリを送信した時, the Search Service shall クエリをsemantic_query、filters（motif_tags, color_tags）、boosts（brightness等）に分解する
2. When クエリ分解が完了した時, the Search Service shall color_tagsおよびmotif_tagsに対するpayloadフィルタを構築してQdrantのprefilterとして適用する
3. When prefilterが構築された時, the Search Service shall semantic_queryをSigLIP2テキスト埋め込みに変換し、image_semanticベクトルに対してコサイン類似度検索を実行する
4. When ベクトル検索結果が返された時, the Search Service shall 軽量リランキング（vector_similarity 70%, motif_match 15%, color_match 10%, brightness_affinity 5%のスコア合成）を適用する
5. The Search Service shall 検索結果にヒット理由（match_reasons）を含める
6. The Search Service shall `POST /api/artworks/search` エンドポイントを提供し、query（文字列）とlimit（数値、デフォルト24）をパラメータとして受け付ける

### Requirement 4: クエリパーサー
**Objective:** As a エンドユーザー, I want 自然言語クエリが自動的に構造化されて検索に使われるようにしたい, so that 複雑なフィルタ構文を意識せずに直感的に検索できる

#### Acceptance Criteria
1. When 自然言語クエリが入力された時, the Query Parser shall ムード表現（やさしい、静か、透明感など）をsemantic_queryとして抽出する
2. When 自然言語クエリに色表現が含まれる時, the Query Parser shall 色名をcolor_tagsフィルタ値（英語正規化形: green, gold等）に変換する
3. When 自然言語クエリにモチーフ表現が含まれる時, the Query Parser shall モチーフをmotif_tagsフィルタ値に変換する
4. When クエリから明るさに関する表現が検出された時, the Query Parser shall brightness_scoreの下限値をboostsとして設定する
5. The Query Parser shall 分解結果をJSON形式（semantic_query, filters, boosts）で出力する

### Requirement 5: オフライン登録API
**Objective:** As a システム管理者, I want 個別の作品を手動でインジェスションパイプラインに投入したい, so that バッチ処理を待たずに新規作品を即座に検索可能にできる

#### Acceptance Criteria
1. When `POST /internal/artworks/index`にリクエストが送信された時, the Ingestion Service shall artwork_id, image_url, title, artist_nameを受け取りインジェスションパイプラインを実行する
2. If 指定されたartwork_idが既にQdrantに存在する場合, the Ingestion Service shall 既存のpointを更新する
3. If 画像URLからの取得に失敗した場合, the Ingestion Service shall エラー内容をログに記録し、適切なHTTPエラーレスポンスを返す

### Requirement 6: Docker Compose基盤
**Objective:** As a 開発者, I want Docker Composeで全サービスを一括起動したい, so that ローカル開発環境を容易にセットアップ・再現できる

#### Acceptance Criteria
1. The Docker Compose Configuration shall Qdrant、Ingestion Service、Search Service、モデルサービングの各コンテナを定義する
2. The Docker Compose Configuration shall Appleシリコン（arm64）上で全コンテナが動作する
3. The Docker Compose Configuration shall Qdrantのデータをnamed volumeで永続化する
4. While Ingestion Serviceが実行中の場合, the Docker Compose Configuration shall GPU/MLXリソースへのアクセスを許可する設定を含む

### Requirement 7: Taxonomy管理
**Objective:** As a 開発者, I want モチーフ・ムード・スタイルの語彙を統制したい, so that VLM出力の揺れを吸収し、一貫性のあるフィルタリングが可能になる

#### Acceptance Criteria
1. The Taxonomy Mapper shall Qwen2.5-VLの出力するモチーフ候補を正規化済みモチーフタグに変換する
2. The Taxonomy Mapper shall ムード表現を定義済みムード語彙セットにマッピングする
3. The Taxonomy Mapper shall 不要・冗長なタグを除去するフィルタリングルールを適用する
4. The Taxonomy Mapper shall taxonomy_versionをpayloadに記録し、バージョン管理を可能にする

### Requirement 8: エラーハンドリングと監視
**Objective:** As a システム管理者, I want インジェスションや検索の失敗を検知・対処したい, so that システムの安定運用と問題の迅速な特定ができる

#### Acceptance Criteria
1. If VLMモデルの推論に失敗した場合, the Ingestion Service shall エラーをログに記録し、該当作品をスキップして残りの処理を継続する
2. If Qdrantへの接続に失敗した場合, the Search Service shall 適切なHTTPエラーレスポンス（503）を返す
3. The Ingestion Service shall 各バッチ処理の開始・終了・処理件数・エラー件数をログに記録する
4. If SigLIP2の埋め込み生成に失敗した場合, the Ingestion Service shall 該当作品をエラーキューに記録し、次回バッチで再試行する
