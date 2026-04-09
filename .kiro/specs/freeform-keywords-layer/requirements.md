# Requirements Document

## Introduction
既存の画像検索システムでは、VLM（Qwen2.5-VL）が出力するモチーフ候補のうち、Taxonomy定義（32語）に一致しないものは破棄されている。これにより、「灯台」「風車」「ハンモック」といったロングテールのモチーフが検索で活用されない。本機能では2つの施策を同時に実施する：(1) Met Museum のCC0タグ語彙（1,077語）をベースにmotif_vocabularyを32語→約815語へ拡張し、Taxonomy層のカバレッジを大幅に向上させる。(2) それでもTaxonomyに一致しないVLM出力を `freeform_keywords` として保持する第3層を追加する。「filterできるモチーフは限定する。対応できるモチーフ自体は限定しない」設計を実現する。

## Requirements

### Requirement 1: freeform_keywords の収集と保存
**Objective:** As a 開発者, I want VLMが出力したモチーフ候補のうちTaxonomyに一致しなかったものを freeform_keywords として保持したい, so that ロングテールのモチーフ情報が破棄されずに検索で活用できる

#### Acceptance Criteria
1. When Taxonomy Mapperがモチーフ候補を正規化した時, the Taxonomy Mapper shall motif_vocabularyおよびmotif_synonymsに一致しなかった候補を freeform_keywords として収集する
2. The Taxonomy Mapper shall freeform_keywords からストップワード（definitions.jsonのstopwords）に該当する語を除外する
3. The Taxonomy Mapper shall freeform_keywords から1文字以下および50文字超の語を除外する
4. The Taxonomy Mapper shall freeform_keywords の重複を除去し、すべて小文字に正規化する
5. When freeform_keywords が収集された時, the Ingestion Service shall ArtworkPayload の freeform_keywords フィールドにリストとして保存する
6. If すべてのモチーフ候補がTaxonomyに一致した場合, the Taxonomy Mapper shall freeform_keywords を空リストとして返す

### Requirement 2: Qdrant payloadスキーマの拡張
**Objective:** As a 開発者, I want freeform_keywords をQdrant payloadに保存しインデックスを作成したい, so that 将来的なフィルタリングやマッチングに利用できる

#### Acceptance Criteria
1. The Qdrant Collection shall 各pointのpayloadに freeform_keywords フィールド（文字列のリスト）を含む
2. The Qdrant Collection shall freeform_keywords に対してKEYWORD型のpayloadインデックスを作成する
3. While 既存のコレクションにfreeform_keywordsインデックスが存在しない場合, the Ingestion Service shall コレクション再作成時にインデックスを自動生成する

### Requirement 3: リランキングでの freeform_keywords 活用
**Objective:** As a エンドユーザー, I want 検索クエリに含まれる語が freeform_keywords と一致した場合にスコアが向上してほしい, so that Taxonomy外のモチーフでも関連する作品が上位に表示される

#### Acceptance Criteria
1. When 検索リランキングが実行された時, the Reranker shall 候補作品の freeform_keywords とクエリのトークンを照合し、一致度スコア（0.0-1.0）を算出する
2. The Reranker shall スコア合成の重みを vector_similarity 65%、motif_match 15%、color_match 10%、brightness_affinity 5%、freeform_keywords_match 5% とする
3. When freeform_keywords の一致が検出された時, the Reranker shall match_reasons に「キーワード一致」を追加する
4. If 候補作品に freeform_keywords が存在しない場合, the Reranker shall freeform_keywords_match スコアを 0.0 とする

### Requirement 5: motif_vocabulary の拡張（32語→約815語）
**Objective:** As a 開発者, I want motif_vocabularyをMet Museum CC0タグ語彙ベースで拡張したい, so that VLM出力のモチーフ候補がTaxonomyに一致する確率が大幅に向上し、freeform_keywordsに落ちる語が減る

#### Acceptance Criteria
1. The Taxonomy definitions.json shall motif_vocabularyをMet Museum タグ語彙（ビジュアルモチーフ＋抽象概念カテゴリ、約795語）と既存32語の和集合である約815語に拡張する
2. The Taxonomy definitions.json shall Met タグの学名表記を一般名に正規化して収録する（例: Bambusoideae→bamboo, Cupressus→cypress, Panthera pardus→leopard）
3. The Taxonomy definitions.json shall 固有名詞（人名・神名・歴史人物 約251語）、言語・文字体系（12語）、宗教的イベント（17語）を motif_vocabulary に含めない
4. When 既存のsynonymが新しいvocabulary語と衝突する場合（例: cloud→sky, forest→tree, hill→mountain）, the Taxonomy definitions.json shall 該当synonymを削除し、両方を独立したvocabulary語として扱う
5. The Taxonomy definitions.json shall 新しいvocabulary語に対する基本的なsynonym（複数形→単数形など）を定義する
6. The Taxonomy definitions.json shall taxonomy_versionを更新する（例: v1→v2）

### Requirement 6: Query Parserの日本語モチーフマッピング拡張
**Objective:** As a エンドユーザー, I want 拡張された語彙に対応する日本語モチーフ表現で検索できるようにしたい, so that 「城」「灯台」「蝶」などの新しいモチーフでもフィルタ検索が機能する

#### Acceptance Criteria
1. The Query Parser shall 既存の24語の日本語→英語モチーフマッピングを維持する
2. The Query Parser shall 検索で頻出する日本語モチーフ表現を追加する（城→castle, 猫→cat, 犬→dog, 馬→horse, 蝶→butterfly, 灯台→lighthouse, 虹→rainbow, 滝→waterfall 等）
3. The Query Parser shall 拡張後も既存のクエリ分解ロジック（色・明るさ・ムード抽出）に影響を与えない
4. While 日本語マッピングが定義されていないモチーフの場合, the Search Service shall ベクトル検索（SigLIP2テキスト埋め込み）で対応する


