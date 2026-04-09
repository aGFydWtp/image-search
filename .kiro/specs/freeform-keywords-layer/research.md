# Research & Design Decisions

## Summary
- **Feature**: `freeform-keywords-layer`
- **Discovery Scope**: Extension
- **Key Findings**:
  - Met Museum タグ語彙（CC0, Wikidata Q106727050）から812語のビジュアルモチーフ＋抽象概念を抽出済み。既存32語との統合で約815語に拡張可能
  - 既存 synonym 13件が新 vocabulary と衝突する（cloud→sky, forest→tree, hill→mountain, building→house, child/man/woman→figure 等）。これらを独立語彙に分離する必要あり
  - freeform_keywords は既存 `_normalize_list` ロジックの「rejected candidates」として自然に実装可能。新メソッド1つの追加で対応できる

## Research Log

### Met Museum タグ語彙の品質と適合性
- **Context**: motif_vocabulary を32語から拡張するための外部語彙ソースの調査
- **Sources Consulted**: Wikidata SPARQL (Q106727050), Met Museum API, Getty AAT, Iconclass
- **Findings**:
  - Met Museum は1,077語のタグ語彙を持ち、CC0ライセンスで利用可能
  - 内訳: ビジュアルモチーフ712語、抽象概念83語、固有名詞251語、宗教イベント17語、言語12語
  - 各タグは Getty AAT および Wikidata にリンク済みで品質保証あり
  - 学名表記（Bambusoideae, Panthera pardus等）は一般名への変換が必要（21件）
- **Implications**: ビジュアルモチーフ＋抽象概念（約795語）を採用。固有名詞・言語・宗教イベントは VLM 出力との親和性が低いため除外

### 既存 synonym 衝突の分析
- **Context**: 新 vocabulary 語と既存 motif_synonyms の衝突解消
- **Sources Consulted**: `shared/taxonomy/definitions.json` の現行定義
- **Findings**:
  - 衝突する synonym: cloud→sky, forest→tree, hill→mountain, building→house, ocean→sea, child→figure, man→figure, woman→figure, person→figure, people→figure, moon→moon, sun→sun, rain→rain, snow→snow, stream→river
  - Met 語彙では cloud/sky, forest/tree, hill/mountain, man/woman/child はそれぞれ独立タグ
  - 粒度を上げることで検索精度が向上する（例：「雲」で検索して「空」全般がヒットする問題を解消）
- **Implications**: 衝突する synonym を削除し、双方を独立 vocabulary 語として登録。figure は維持しつつ man/woman/child も追加

### Qdrant KEYWORD インデックスのスケーラビリティ
- **Context**: motif_vocabulary を815語に拡張した場合の Qdrant パフォーマンス影響
- **Sources Consulted**: Qdrant ドキュメント（payload filtering, indexing）
- **Findings**:
  - KEYWORD インデックスは内部的に inverted index を使用。語彙数の増加はインデックスサイズに影響するが、検索パフォーマンスへの影響は軽微
  - MatchAny クエリは語彙数に依存せず、候補 point 数に依存
  - 1,000語以下の語彙であればパフォーマンス懸念なし
- **Implications**: 特別な対策不要。既存の KEYWORD インデックス構成をそのまま利用

## Design Decisions

### Decision: freeform_keywords の収集対象を motif_candidates のみに限定
- **Context**: VLM は motif/mood/style/subject の4カテゴリで候補を出力する。どのカテゴリの rejected candidates を freeform_keywords に含めるか
- **Alternatives Considered**:
  1. 全4カテゴリの rejected candidates を含める
  2. motif_candidates のみ
- **Selected Approach**: motif_candidates のみ
- **Rationale**: mood/style/subject は既存 taxonomy のカバレッジが十分（20/20/15語）。motif が最も語彙の幅が広く、ロングテール問題が顕著
- **Trade-offs**: mood の珍しい表現（例: "bittersweet"）は freeform_keywords に入らないが、ベクトル検索でカバー可能
- **Follow-up**: 運用後に mood/style の rejected candidates も必要か評価

### Decision: Reranker の重み配分変更
- **Context**: freeform_keywords_match を追加するにあたり、既存重みの再配分が必要
- **Alternatives Considered**:
  1. vector 0.70→0.65, freeform 0.05（vector から捻出）
  2. motif 0.15→0.10, freeform 0.05（motif から捻出）
  3. 全体を再配分
- **Selected Approach**: vector 0.70→0.65, freeform 0.05
- **Rationale**: motif_vocabulary が815語に拡張されるため motif_match の重要性は維持すべき。vector から5%移動が最も影響が小さい
- **Trade-offs**: ベクトル類似度の影響がわずかに低下するが、freeform boost で補完
- **Follow-up**: A/Bテストで最適重みを検証

### Decision: synonym 衝突の解消方針
- **Context**: cloud→sky のような既存 synonym が、新 vocabulary では独立語として扱われる
- **Alternatives Considered**:
  1. synonym を維持し、cloud は引き続き sky にマップ
  2. synonym を削除し、cloud と sky を独立語彙にする
- **Selected Approach**: synonym を削除し独立語彙化
- **Rationale**: Met Museum の粒度に合わせることで、VLM 出力の情報損失を防ぐ。「cloud のある作品」と「sky のある作品」は異なる検索意図
- **Trade-offs**: 既存インデックスデータとの互換性なし（再インジェスション必要）
- **Follow-up**: taxonomy_version を v2 に更新し、再インジェスションを実施

## Risks & Mitigations
- **VLM 出力と815語語彙の一致率が未知** — 再インジェスション後にマッチ率を計測し、必要に応じて synonym を追加
- **日本語 Query Parser のマッピング不足** — v1 では頻出50語程度を追加。残りはベクトル検索でカバー。段階的に拡張
- **既存テストの破壊** — デフォルト値（[]）によるモデル後方互換性を確保。taxonomy_version による切り分け

## References
- [Met Museum Tagging Vocabulary (Wikidata Q106727050)](https://www.wikidata.org/wiki/Q106727050)
- [Met Museum Open Access (GitHub)](https://github.com/metmuseum/openaccess)
- [Wikidata GLAM Met Tags](https://www.wikidata.org/wiki/Wikidata:GLAM/Metropolitan_Museum_of_Art/Tag_vocabulary_in_Wikidata)
- [Getty AAT](https://www.getty.edu/research/tools/vocabularies/aat/)
- [Qdrant Payload Filtering](https://qdrant.tech/documentation/search/filtering/)
- [Qdrant Payload Indexes](https://qdrant.tech/documentation/manage-data/payload/)
