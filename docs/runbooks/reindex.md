# 再インデックス運用 Runbook

本ドキュメントは Qdrant Blue/Green 再インデックスの運用手順を **人間と LLM の両方が辿れる** 形で集約する単一ソース・オブ・トゥルースである。design.md は「何が作られるか」、本ファイルは「どう動かすか」を担う。

全シナリオは以下の固定構造を持つ:

- `### 前提条件` — 実行前に満たすべき状態
- `### コマンド` — 実行コマンド (bash コードブロック)
- `### 期待ログ` — 成功時に出力される `event` キー (text コードブロック、1 行 1 キー)
- `### 成功判定` — 完了を確認する方法
- `### 失敗時アクション` — 異常時の対処
- `### 成功判定チェックリスト` — コピー可能なチェックボックスリスト

`event` ラベル定義は `.kiro/specs/zero-downtime-reindex/design.md` の「イベントキー一覧」を正とする。

シナリオ一覧:

| # | シナリオ | 主な CLI |
|---|---------|---------|
| 1 | 初期エイリアス作成 (初回セットアップのみ) | `reindex init-alias` |
| 2 | 新規再インデックスの実行 | `reindex run --target-version vN` |
| 3 | ドライランで切替計画を確認 | `reindex run ... --dry-run` |
| 4 | 再インデックス期間中のキャッチアップ | `reindex catchup --source X --target Y` |
| 5 | ロールバック | `reindex rollback --to vN-1` |
| 6 | 旧コレクションの安全な削除 | `reindex drop-collection artworks_vN-1` |
| 7 | 検索サービスの健全性確認 | `curl .../readyz` |
| 8 | 障害時の判断フロー | - |

---

## 1. 初期エイリアス作成 (初回セットアップのみ)

### 前提条件

- Qdrant が起動中で、既存物理コレクション (例: `artworks_v1`) にデータが入っている
- エイリアス `artworks_current` がまだ定義されていない
- 検索サービスはまだ起動していない、または起動失敗状態 (`search.alias.unresolved`)

### コマンド

```bash
docker compose run --rm ingestion python -m services.ingestion.reindex init-alias
```

### 期待ログ

```text
reindex.alias.initialized
```

既にエイリアスが存在する場合は no-op で以下が出る。

```text
reindex.alias.init_skipped
```

### 成功判定

- 終了コード 0
- Qdrant の `get_aliases` に `artworks_current → artworks_v1` (または `QDRANT_COLLECTION`) が現れる
- `docker compose restart search` 後、`/readyz` が 200 を返す

### 失敗時アクション

| 発生状況 | 対処 |
|---------|------|
| Qdrant 接続エラー | Qdrant コンテナの状態 / `QDRANT_API_KEY` を確認 |
| 対象物理コレクションが存在しない | 先にバッチインジェスション (`docker compose run --rm ingestion python -m services.ingestion.run`) で `QDRANT_COLLECTION` を作成 |

### 成功判定チェックリスト

```markdown
- [ ] `event=reindex.alias.initialized` または `reindex.alias.init_skipped` が出力された
- [ ] Qdrant のエイリアス一覧に `artworks_current` が含まれる
- [ ] Search Service の `/readyz` が 200 を返す
```

---

## 2. 新規再インデックスの実行

### 前提条件

- Qdrant が起動中で、エイリアス `artworks_current` が物理コレクション (例: `artworks_v1`) を指している
- 検索サービスが稼働中で `/readyz` が 200 を返している
- 埋め込みサービス (SigLIP2, port 8100) と LM Studio (port 1234) がホスト側で起動している
- Firebase Storage の認証情報が `config/firebase-credentials.json` に配置されている
- 新しい物理コレクション名 (例: `artworks_v2`) が未使用である

### コマンド

```bash
docker compose run --rm ingestion python -m services.ingestion.reindex run \
    --target-version v2
```

追加フラグ:

```bash
# 同名コレクションが残存している場合、削除して再作成する
docker compose run --rm ingestion python -m services.ingestion.reindex run \
    --target-version v2 --force-recreate

# 検証比率を上書き (既定 0.9)
docker compose run --rm ingestion python -m services.ingestion.reindex run \
    --target-version v2 --sample-ratio 0.85

# 緊急時のエスケープ: 検証を完全に省略 (推奨しない、WARN ログが残る)
docker compose run --rm ingestion python -m services.ingestion.reindex run \
    --target-version v2 --skip-validation
```

### 期待ログ

```text
reindex.started
reindex.collection.created
reindex.progress
reindex.validation.passed
reindex.alias.swap
```

フラグ別の追加ログ:

```text
reindex.collection.recreated   (--force-recreate 指定時のみ、既存削除)
reindex.validation.skipped     (--skip-validation 指定時のみ、WARNING)
```

### 成功判定

- 終了コード 0
- `/readyz` 応答の `collection` フィールドが新物理名 (例: `artworks_v2`) に切り替わっている
- 検索 API (`POST /api/artworks/search`) が引き続き 200 を返す

### 失敗時アクション

| 発生状況 | 対処 |
|---------|------|
| `reindex.validation.failed` が出て終了コード 1 | 検証失敗。新コレクションは残るが alias は切り替わっていない。件数比不足が原因なら `--sample-ratio` を調整、または populate を再実行するために `--force-recreate` で再開 |
| `reindex.alias.swap.failed` が出て終了コード 1 | Qdrant との通信失敗。Qdrant のログ確認、再試行 |
| `reindex.samples.load_failed` が出て終了コード 2 | `config/reindex_samples.json` の構文 / スキーマを確認 |
| populate 途中で例外 → 終了コード 1 | 新コレクションは残る。原因 (Firebase/VLM/Embedding) を解消し、同じ `--target-version` で再実行 (冪等) |

### 成功判定チェックリスト

```markdown
- [ ] `event=reindex.alias.swap` ログが出力された
- [ ] `curl http://localhost:8000/readyz` が 200、`collection` が新物理名
- [ ] 任意の検索 API リクエストが 200 で結果を返す
- [ ] 旧物理コレクションが Qdrant に残っている (ロールバック用)
```

---

## 3. ドライランで切替計画を確認

### 前提条件

- 「1. 新規再インデックスの実行」と同じ前提を満たす
- 新しい物理コレクション名が未使用、または `--force-recreate` で再生成して問題ない

### コマンド

```bash
docker compose run --rm ingestion python -m services.ingestion.reindex run \
    --target-version v2 --dry-run
```

### 期待ログ

```text
reindex.started
reindex.collection.created
reindex.progress
reindex.validation.passed
reindex.dry_run
```

> 切替ログ `reindex.alias.swap` は出力されない。

### 成功判定

- 終了コード 0
- `reindex.dry_run` ログに `validation_passed: true`
- `/readyz` の `collection` は従来物理名のまま (切替されていない)

### 失敗時アクション

| 発生状況 | 対処 |
|---------|------|
| `reindex.validation.failed` | ドライランでも検証は実行される。失敗原因を調査してから本番実行 |
| populate 途中で例外 | 新コレクションは残る。調査してから再実行 |

### 成功判定チェックリスト

```markdown
- [ ] `event=reindex.dry_run` ログが出力された
- [ ] `event=reindex.alias.swap` は出力されていない
- [ ] `/readyz` の `collection` が従来物理名のまま
- [ ] 新コレクション側は populate 完了状態で保持されている
```

---

## 4. 再インデックス期間中のキャッチアップ

### 前提条件

- 新コレクションが作成済で、validate → swap の直前まで進んでいる
- その期間中に旧コレクション (`artworks_v1`) へ差分 ingestion で新規 artwork が追加されている可能性がある
- 新コレクションを最新状態に揃えてから swap したい

### コマンド

```bash
docker compose run --rm ingestion python -m services.ingestion.reindex catchup \
    --source artworks_v1 --target artworks_v2
```

### 期待ログ

```text
reindex.catchup.started
reindex.catchup.progress
reindex.catchup.completed
```

### 成功判定

- 終了コード 0
- `reindex.catchup.completed` ログの `copied_count` が旧コレクションの件数と一致

### 失敗時アクション

| 発生状況 | 対処 |
|---------|------|
| `reindex.catchup.invalid` | `source` と `target` が同じ、または `batch_size` が 0 以下。引数を修正 |
| `reindex.catchup.failed` | Qdrant 通信失敗。再実行は冪等 (point_id 決定論的) なので安全に繰り返せる |

### 成功判定チェックリスト

```markdown
- [ ] `event=reindex.catchup.completed` が出力された
- [ ] `copied_count` が旧コレクションの件数と一致する
- [ ] 新コレクション側の count が同じ件数まで進んでいる
```

---

## 5. ロールバック

### 前提条件

- 直近の swap で問題が発覚した
- 切替前の物理コレクション (例: `artworks_v1`) が削除されていない

### コマンド

```bash
docker compose run --rm ingestion python -m services.ingestion.reindex rollback \
    --to v1
```

### 期待ログ

```text
reindex.rollback
```

### 成功判定

- 終了コード 0
- `/readyz` 応答の `collection` が旧物理名 (例: `artworks_v1`) に戻っている
- 検索 API が旧挙動で応答している

### 失敗時アクション

| 発生状況 | 対処 |
|---------|------|
| `reindex.rollback.failed` 終了コード 1 | 戻り先コレクションが既に削除されている。別の世代へ `rollback --to v0` を試す。全て失われていれば再インデックス (手順 1) で復旧 |

### 成功判定チェックリスト

```markdown
- [ ] `event=reindex.rollback` ログが出力された
- [ ] `curl http://localhost:8000/readyz` が 200、`collection` が旧物理名
- [ ] 検索 API が通常応答を返している
```

---

## 6. 旧コレクションの安全な削除

### 前提条件

- 切替後十分な観察期間 (例: 24 時間) が経過し、新コレクションで問題が起きていない
- 削除対象のコレクションはエイリアスの現行ターゲットではない

### コマンド

```bash
docker compose run --rm ingestion python -m services.ingestion.reindex drop-collection \
    artworks_v0
```

### 期待ログ

```text
reindex.collection.dropped
```

### 成功判定

- 終了コード 0
- Qdrant に対象物理コレクションが存在しない

### 失敗時アクション

| 発生状況 | 対処 |
|---------|------|
| `reindex.collection.drop_refused` 終了コード 1 | 指定したコレクションが現行エイリアスのターゲットになっている。削除は行われない。正しい世代名を指定 |
| 引数が `^artworks_[a-zA-Z0-9_-]+$` に合わない | argparse エラーで終了コード 2。物理コレクション名の全体 (`artworks_v0` など) を指定する |

### 成功判定チェックリスト

```markdown
- [ ] `event=reindex.collection.dropped` ログが出力された
- [ ] 削除対象がエイリアス現行ターゲットでないことを確認済み
- [ ] 検索 API / `/readyz` に影響なし
```

---

## 7. 検索サービスの健全性確認

### 前提条件

- 検索サービスが起動中 (`docker compose up -d search` 実行済)

### コマンド

```bash
# Liveness: プロセス生存のみ
curl -s http://localhost:8000/healthz

# Readiness: エイリアス解決 + count 成功
curl -s http://localhost:8000/readyz | python -m json.tool
```

### 期待ログ

正常系では `readyz` がアクセスされても追加ログは出ない。異常系では以下。

```text
search.alias.unresolved
search.readiness.failed
```

### 成功判定

- `/healthz` が `{"status": "ok"}` で 200
- `/readyz` が `{"alias": ..., "collection": ..., "points_count": N}` で 200

### 失敗時アクション

| 発生状況 | 対処 |
|---------|------|
| `/readyz` 503 + `event=search.alias.unresolved` | エイリアス未定義。手順「エイリアス初期化」 (README 3.5) を実行 |
| `/readyz` 503 + `event=search.readiness.failed` | Qdrant 不通または権限エラー。Qdrant コンテナ状態と `QDRANT_API_KEY` を確認 |
| 起動時に CRITICAL `search.alias.unresolved` | 同上、エイリアス未定義。`init-alias` を先に実行してから search を再起動 |

### 成功判定チェックリスト

```markdown
- [ ] `/healthz` が 200 を返す
- [ ] `/readyz` が 200 で `alias`/`collection`/`points_count` を含む
- [ ] 上記応答に API キーなどの秘密情報が含まれていない
```

---

## 8. 障害時の判断フロー

### 前提条件

- 構造化ログを `event` ラベルで検索できる環境 (ローカル: `docker compose logs`、本番: Cloud Logging)

### コマンド

```bash
# 直近の運用イベントを event ラベルで絞る (jq 推奨)
docker compose logs --since 15m --no-log-prefix ingestion search \
    | jq -r 'fromjson? | ."logging.googleapis.com/labels".event // empty' \
    | sort | uniq -c

# jq が無い環境でのフォールバック (labels 内のスペース許容した緩い正規表現)
docker compose logs --since 15m ingestion search \
    | grep -oE '"event":\s*"[^"]+"' | sort | uniq -c
```

### 期待ログ

ハッピーパスでは以下のいずれか 1 系列のみが観測される。

```text
reindex.started
reindex.collection.created
reindex.progress
reindex.validation.passed
reindex.alias.swap
```

失敗系のイベントキー (`.failed` 系一覧):

```text
reindex.validation.failed
reindex.alias.swap.failed
reindex.rollback.failed
reindex.catchup.failed
reindex.samples.load_failed
reindex.aborted
search.alias.unresolved
search.readiness.failed
ingestion.alias.mismatch
```

### 成功判定

判断フロー (上から順に評価):

1. **`reindex.alias.swap.failed`** がある → Qdrant 側の問題。Qdrant ログを確認し、再 `run --target-version ...` で切替のみ再試行
2. **`reindex.validation.failed`** がある → 件数比不足またはサンプル検索例外。`--sample-ratio` 調整 or populate 再実行で改善
3. **`reindex.aborted`** のみがある → 検証失敗で切替を踏みとどまった状態。新コレクションは残っているので `rollback` 不要
4. **`search.alias.unresolved`** が継続 → エイリアス未定義または削除された。`init-alias` または `rollback` で復旧
5. **`ingestion.alias.mismatch`** が出ている → env `QDRANT_COLLECTION` と alias 先が不一致。実害はないが env を最新に更新
6. **`reindex.catchup.failed`** が出ている → catchup が途中終了。再実行は冪等なので同じコマンドを再投入

### 失敗時アクション

判断フローで該当項目が不明な場合:

1. 直前の `event=reindex.started` / `reindex.rollback` / `reindex.alias.swap` を特定し、時系列で何が起きたか再構成
2. `/readyz` を叩いて現在のエイリアスターゲット物理名を確認
3. Qdrant に直接接続して `get_aliases` / `collection_exists` で実状態を把握
4. 不明なら rollback で確実に戻れる世代に復帰 (旧コレクション未削除の場合のみ)

### 成功判定チェックリスト

```markdown
- [ ] 発生したイベントキーを特定した
- [ ] 判断フロー 1-6 のいずれかに分類できた
- [ ] `/readyz` で現在のエイリアスターゲットを確認した
- [ ] 必要に応じて rollback / init-alias / catchup のいずれかを実行した
- [ ] 再発防止のためログまたは Issue に記録した
```
