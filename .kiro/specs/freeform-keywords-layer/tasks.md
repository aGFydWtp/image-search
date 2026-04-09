# Implementation Plan

- [x] 1. Taxonomy 語彙の拡張（definitions.json v2）
- [x] 1.1 motif_vocabulary を Met Museum タグベースで815語に拡張する
  - `config/met_museum_tags_filtered.json` の812語と既存32語を統合し、重複排除した語彙リストを生成する
  - 学名表記を一般名に正規化する（Bambusoideae→bamboo, Cupressus→cypress, Panthera pardus→leopard 等21件）
  - 固有名詞、言語・文字体系、宗教的イベントが含まれていないことを検証する
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 1.2 motif_synonyms の衝突解消と新規追加
  - 新 vocabulary 語と衝突する既存 synonym を削除する（cloud→sky, forest→tree, hill→mountain, building→house, person→figure, people→figure, woman→figure, man→figure, child→figure）
  - 複数形→単数形の基本 synonym を新語彙に対して追加する（buildings→building, hills→hill, forests→forest, clouds→cloud, children→child, wolves→wolf 等）
  - ocean→sea, waves→sea 等の既存有効 synonym が維持されていることを確認する
  - taxonomy_version を "v1" から "v2" に更新する
  - _Requirements: 5.4, 5.5, 5.6_

- [x] 2. データモデルとパイプラインへの freeform_keywords 組み込み
- [x] 2.1 (P) NormalizedTags と ArtworkPayload に freeform_keywords フィールドを追加する
  - NormalizedTags モデルに `freeform_keywords: list[str]` フィールドを追加する
  - ArtworkPayload モデルに `freeform_keywords: list[str]` フィールドを subject_tags の後に追加する
  - _Requirements: 1.1, 1.5_

- [x] 2.2 (P) TaxonomyMapper に freeform_keywords 収集ロジックを実装する
  - `_collect_freeform_keywords` メソッドを追加し、motif_candidates のうち vocabulary/synonym に一致しなかった候補を収集する
  - ストップワード除外、1文字以下・50文字超の除外、小文字正規化、重複排除のフィルタリングを実装する
  - `normalize` メソッドで `_collect_freeform_keywords` を呼び出し、結果を NormalizedTags.freeform_keywords に設定する
  - 全候補が Taxonomy 一致した場合は空リストを返すことを確認する
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

- [x] 2.3 IngestionService で freeform_keywords を ArtworkPayload に渡す
  - `_run_pipeline` の ArtworkPayload 構築箇所に `freeform_keywords=normalized.freeform_keywords` を追加する
  - 2.1 と 2.2 の完了が前提
  - _Requirements: 1.5_

- [ ] 3. Qdrant スキーマ拡張
- [ ] 3.1 QdrantRepository の ensure_collection に freeform_keywords KEYWORD インデックスを追加する
  - tag_field ループに "freeform_keywords" を追加し、KEYWORD 型のペイロードインデックスを作成する
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 4. 検索層の freeform_keywords 対応
- [ ] 4.1 (P) Reranker に freeform_keywords マッチスコアを組み込む
  - スコア合成の重み定数を変更する（vector 0.70→0.65、freeform 0.05 を新設）
  - `_calc_freeform_match` メソッドを追加し、semantic_query トークンと候補の freeform_keywords の交差率を算出する
  - `rerank` メソッドのスコア合成に freeform スコアを追加する
  - freeform 一致時に match_reasons に「キーワード一致」を追加する
  - freeform_keywords が存在しない候補のスコアを 0.0 にする
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 4.2 (P) Query Parser の日本語モチーフマッピングを拡張する
  - 既存24語のマッピングを維持したまま、頻出する約30語の日本語→英語マッピングを追加する（猫→cat, 犬→dog, 馬→horse, 蝶→butterfly, 城→castle, 灯台→lighthouse, 虹→rainbow, 滝→waterfall 等）
  - vocabulary 分離に伴い、既存マッピング「森→tree」を「森→forest」に変更する
  - 色・明るさ・ムード抽出のロジックに影響がないことを確認する
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 5. テスト
- [ ] 5.1 TaxonomyMapper の freeform_keywords 収集テストを追加する
  - 非一致候補の収集、stopword 除外、長さフィルタ、重複排除、synonym 除外、全一致時の空リスト（6ケース）
  - 815語 vocabulary での正規化動作と新 synonym の解決を検証する
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 5.4, 5.5_

- [ ] 5.2 (P) Reranker の freeform boost テストを追加する
  - freeform 一致ありでスコアが向上することを検証する
  - freeform_keywords なしの候補でスコアが 0.0 であることを検証する
  - match_reasons に「キーワード一致」が追加されることを検証する
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 5.3 (P) Query Parser の拡張マッピングテストを追加する
  - 新規追加した日本語モチーフ（猫、城、灯台等）が正しく英語タグに変換されることを検証する
  - 既存マッピング（空→sky, 海→sea 等）が維持されていることを検証する
  - 「森」の変更（tree→forest）が反映されていることを検証する
  - _Requirements: 6.1, 6.2, 6.3_

- [ ] 6. マイグレーションと動作確認
- [ ] 6.1 Qdrant コレクションを再作成し、全作品を再インジェスションする
  - 既存コレクションを削除し、freeform_keywords インデックスを含む新スキーマで再作成する
  - 全作品を v2 taxonomy で再インジェスションし、motif_tags と freeform_keywords が正しく生成されることを確認する
  - インジェスション完走後、Qdrant のペイロードに freeform_keywords が含まれていることを確認する
  - _Requirements: 2.1, 2.2, 2.3, 5.1, 5.6_

- [ ] 6.2 検索の E2E 動作確認
  - 日本語クエリ（例：「猫のいる風景」「灯台のある海」）で検索し、拡張モチーフのフィルタが機能することを確認する
  - freeform_keywords を持つ作品に対して、英語キーワードを含むクエリでスコアが向上することを確認する
  - 既存クエリ（「空と山のある穏やかな風景」等）が従来通り動作することを確認する
  - _Requirements: 3.1, 6.2, 6.4_
