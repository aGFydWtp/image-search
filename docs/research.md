方針としては、オフラインで作品特徴を確定 → Qdrant に保存 → オンラインでは「クエリ分解 + フィルタ + ベクトル検索 + 軽い再ランキング」 の形が一番現実的です。Qdrant は named vectors と payload を同じ point に持てるので、今回の「雰囲気はベクトル、色とモチーフはフィルタ」という設計に合っています。SigLIP2 は多言語の vision-language encoder で、画像テキスト検索や zero-shot 分類向けに使えます。Qwen2.5-VL は画像理解に加えて、比較的安定した JSON 出力や位置特定を打ち出しているので、作品ごとの説明・タグ抽出をオフラインで回す役に向いています。  ￼

⸻

v1 アーキテクチャ図

┌─────────────────────────────────────────────────────────────┐
│                        Offline Ingestion                    │
└─────────────────────────────────────────────────────────────┘

 [Artwork Image / Title / Artist / Description]
                     │
                     ▼
        ┌──────────────────────────────┐
        │ 1. Preprocess                │
        │ - 画像正規化                 │
        │ - サムネイル生成             │
        │ - 原本メタデータ整理         │
        └──────────────────────────────┘
                     │
                     ├──────────────────────────────────────┐
                     │                                      │
                     ▼                                      ▼
        ┌──────────────────────────────┐      ┌──────────────────────────────┐
        │ 2. Qwen2.5-VL                │      │ 3. Color Extractor           │
        │ - caption 生成               │      │ - 支配色抽出                 │
        │ - motif 候補抽出             │      │ - brightness/saturation      │
        │ - style / subject 候補抽出   │      │ - color tags 正規化          │
        │ - JSON 構造化                │      └──────────────────────────────┘
        └──────────────────────────────┘
                     │                                      │
                     └──────────────────┬───────────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │ 4. Taxonomy Mapper           │
                         │ - motif 正規化               │
                         │ - mood 語彙への寄せ          │
                         │ - 不要タグ除去               │
                         └──────────────────────────────┘
                                        │
                                        ├──────────────────────────────┐
                                        │                              │
                                        ▼                              ▼
                         ┌──────────────────────────────┐  ┌──────────────────────────────┐
                         │ 5. SigLIP2 Image Embedding   │  │ 6. Optional Text Embedding   │
                         │ - mood/semantic 主ベクトル   │  │ - caption/title 埋め込み     │
                         └──────────────────────────────┘  └──────────────────────────────┘
                                        │                              │
                                        └──────────────┬───────────────┘
                                                       ▼
                                      ┌─────────────────────────────────┐
                                      │ 7. Qdrant                      │
                                      │ point:                         │
                                      │ - named vector: image_semantic │
                                      │ - named vector: text_semantic  │
                                      │ - payload: motif/color/etc     │
                                      └─────────────────────────────────┘


┌─────────────────────────────────────────────────────────────┐
│                        Online Search                        │
└─────────────────────────────────────────────────────────────┘

 [User Query]
   例: 「やさしい感じで、緑と金が入っていて、空っぽい作品」
                     │
                     ▼
        ┌──────────────────────────────┐
        │ A. Query Parser (LLM/Rules)  │
        │ - mood: やさしい             │
        │ - colors: green, gold        │
        │ - motifs: sky                │
        │ - free text: 全体文          │
        └──────────────────────────────┘
                     │
                     ├──────────────────────────────┐
                     │                              │
                     ▼                              ▼
        ┌──────────────────────────────┐  ┌──────────────────────────────┐
        │ B. Filter Builder            │  │ C. SigLIP2 Text Embedding    │
        │ - color filter               │  │ - mood/free text を埋め込み  │
        │ - motif filter               │  └──────────────────────────────┘
        │ - brightness filter          │
        └──────────────────────────────┘
                     │                              │
                     └──────────────┬───────────────┘
                                    ▼
                    ┌────────────────────────────────────┐
                    │ D. Qdrant Search                   │
                    │ - prefilter (payload)             │
                    │ - vector search (image_semantic)  │
                    │ - optional hybrid / multi-stage   │
                    └────────────────────────────────────┘
                                    │
                                    ▼
                    ┌────────────────────────────────────┐
                    │ E. Lightweight Rerank              │
                    │ - exact motif match boost          │
                    │ - color一致 boost                 │
                    │ - caption 文字一致補正            │
                    └────────────────────────────────────┘
                                    │
                                    ▼
                    ┌────────────────────────────────────┐
                    │ F. Response Builder                │
                    │ - 結果一覧                        │
                    │ - 「なぜヒットしたか」を表示      │
                    └────────────────────────────────────┘


⸻

設計意図

1. オフラインとオンラインを分ける理由

Qwen2.5-VL で caption や motif 候補を作る処理は重いので、毎検索時ではなく取り込み時に確定した方が安定します。Qwen2.5-VL は座標や属性の JSON 出力や visual localization を打ち出しているため、構造化メタデータ生成との相性が良いです。  ￼

2. Qdrant をこう使う理由

Qdrant は 1 point に対して 複数の named vectors と payload を持てます。さらに hybrid / multi-stage queries をサポートしているので、まず単純な prefilter + vector search で始め、あとから段階的に検索戦略を強化しやすいです。  ￼

3. DINOv2 を外す理由

前の議論では DINOv2 も候補でしたが、まず SigLIP2 を主ベクトル に絞る方が実装が軽いです。SigLIP2 は多言語・画像テキスト検索向けで、アート検索の「やさしい」「静か」「透明感」といった自然文クエリに寄せやすいからです。  ￼

⸻

Qdrant 前提のデータスキーマ案

1. コレクション名

artworks_v1

2. point の考え方

Qdrant の 1 point = 1作品です。
Qdrant の point は id / vectors / payload を持ちます。今回はこの形にします。  ￼

3. vectors 設計

まず 2 本で十分です。
	•	image_semantic
	•	作品画像から作る主ベクトル
	•	モデル: SigLIP2
	•	用途: 雰囲気・意味検索の主軸
	•	text_semantic
	•	caption / title / artist note から作る補助ベクトル
	•	モデル: SigLIP2 系または互換埋め込み
	•	用途: 補助検索や将来の hybrid 強化

Qdrant は named vectors を point 単位で保持できます。  ￼

4. payload 設計

以下くらいが初期実装でちょうど良いです。

{
  "artwork_id": "art_000123",
  "title": "Evening Light",
  "artist_name": "A. Example",
  "artist_id": "artist_009",
  "year": 2024,
  "medium": "digital painting",
  "license": "internal",
  "image_url": "https://...",
  "thumbnail_url": "https://...",
  "width": 2048,
  "height": 3072,
  "aspect_ratio": 0.6667,

  "caption": "A soft, luminous sky with gentle green and gold tones.",
  "description_source": "qwen2.5-vl",
  "language": "ja",

  "mood_tags": ["やさしい", "明るい", "静かな"],
  "style_tags": ["抽象", "風景寄り"],
  "motif_tags": ["空", "光"],
  "subject_tags": ["雲", "空"],
  "color_tags": ["green", "gold"],
  "palette_hex": ["#A8C66C", "#D9B44A", "#EDE7D1"],

  "brightness_score": 0.78,
  "saturation_score": 0.42,
  "warmth_score": 0.61,

  "is_abstract": true,
  "has_character": false,

  "taxonomy_version": "v1",
  "ingested_at": "2026-03-10T10:00:00Z",
  "updated_at": "2026-03-10T10:00:00Z"
}


⸻

推奨 payload フィールド一覧

必須
	•	artwork_id
	•	title
	•	artist_name
	•	image_url
	•	thumbnail_url
	•	caption
	•	mood_tags
	•	motif_tags
	•	color_tags
	•	brightness_score
	•	saturation_score

あると便利
	•	style_tags
	•	palette_hex
	•	is_abstract
	•	has_character
	•	year
	•	medium
	•	width
	•	height
	•	aspect_ratio

v1 では不要
	•	トークン単位 multivector
	•	複雑な provenance 履歴
	•	複数 taxonomy の完全併存
	•	agent 用の中間推論ログ永続化

⸻

Qdrant コレクションの論理定義イメージ

Qdrant の named vectors を前提にすると、概念的にはこんな形です。

{
  "collection_name": "artworks_v1",
  "vectors": {
    "image_semantic": {
      "size": 768,
      "distance": "Cosine"
    },
    "text_semantic": {
      "size": 768,
      "distance": "Cosine"
    }
  }
}

実際の次元数は、採用する SigLIP2 モデルに合わせて確定してください。Qdrant は collection でベクトル定義を持ち、point ごとに named vector を保持できます。  ￼

⸻

検索時のクエリ分解仕様案

ユーザー入力:
やさしい感じで、緑と金が入っていて、空っぽい作品

parser 出力:

{
  "semantic_query": "やさしい感じ 空 光 穏やか",
  "filters": {
    "motif_tags": ["空"],
    "color_tags": ["green", "gold"]
  },
  "boosts": {
    "brightness_min": 0.55
  }
}

実際の検索手順
	1.	color_tags contains green/gold
	2.	motif_tags contains 空
	3.	brightness_score >= 0.55 を必要なら追加
	4.	その prefilter を Qdrant に渡す
	5.	semantic_query を SigLIP2 テキスト埋め込みにして image_semantic を検索
	6.	上位結果を軽く rerank

Qdrant は payload ベースの filtering と named-vector 検索を組み合わせられます。さらに hybrid / multi-stage query の拡張余地もあります。  ￼

⸻

再ランキング案

重いマルチモーダル reranker まで入れず、まずはスコア合成で十分です。

final_score
= 0.70 * vector_similarity
+ 0.15 * motif_match_score
+ 0.10 * color_match_score
+ 0.05 * brightness_affinity

これでまずは十分です。
Qdrant の multi-stage query を使う余地はありますが、v1 ではアプリ側の rerank で始める方がデバッグしやすいです。Qdrant 自体は multi-stage / hybrid query の拡張をサポートしています。  ￼

⸻

実装上の注意

1. mood_tags は検索主軸にしすぎない

やさしい や 透明感 はタグだけで固定しすぎると表現が死にやすいので、主軸はベクトル、タグは補助がよいです。SigLIP2 は image-text retrieval 向けなので、この役割分担が自然です。  ￼

2. color はベクトルだけに任せない

色は厳密条件が入りやすいので、payload filter にするのが安定です。Qdrant の filtering との相性が良いです。  ￼

3. Qwen2.5-VL の出力はそのまま保存しない

Qwen2.5-VL は強力ですが、出力語彙は揺れるので、taxonomy mapper で正規化した上で motif_tags や style_tags に落とすのが大事です。JSON 出力が安定している点は活かしつつ、保存前の正規化層を必ず入れるべきです。  ￼

⸻

最小 API 例

オフライン登録

POST /internal/artworks/index

{
  "artwork_id": "art_000123",
  "image_url": "https://...",
  "title": "Evening Light",
  "artist_name": "A. Example"
}

検索

POST /api/artworks/search

{
  "query": "やさしい感じで、緑と金が入っていて、空っぽい作品",
  "limit": 24
}

レスポンス

{
  "parsed_query": {
    "semantic_query": "やさしい 穏やか 空 光",
    "filters": {
      "motif_tags": ["空"],
      "color_tags": ["green", "gold"]
    }
  },
  "items": [
    {
      "artwork_id": "art_000123",
      "title": "Evening Light",
      "artist_name": "A. Example",
      "thumbnail_url": "https://...",
      "match_reasons": [
        "やさしい雰囲気が近い",
        "空モチーフ一致",
        "緑・金の色味一致"
      ]
    }
  ]
}


⸻

まとめ

- オフライン: Qwen2.5-VL で caption / motif 候補抽出、色抽出、SigLIP2 埋め込み生成
- 保存: Qdrant に image_semantic, text_semantic, payload を保存
- オンライン: クエリを semantic_query + filters に分解し、prefilter + vector search
- 表示: 軽い rerank とヒット理由表示

この形なら、過剰に複雑にせず、あとから
DINOv2 追加、hybrid 強化、multi-stage query、画像アップロード検索 に拡張しやすいです。  ￼