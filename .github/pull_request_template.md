<!--
PR の説明を上書きして記入してください。
-->

## 概要

<!-- この PR が何を変えるか、なぜ必要かを 1-3 文で -->

## 変更点

<!-- 箇条書き、変更範囲が分かる粒度で -->

-

## テスト

<!-- 追加/変更したテスト、手動確認した手順 -->

-

## チェックリスト

- [ ] `pytest` が通る (ローカル / CI)
- [ ] 新規コードに対するテストを追加した
- [ ] リポジトリ既存の pre-existing 失敗以外の回帰がないことを確認した

### Spec 駆動開発 (`.kiro/specs/*`)

- [ ] 関連する `requirements.md` / `design.md` / `tasks.md` を同じ PR で更新した (該当する変更がある場合)
- [ ] `/kiro:spec-status {feature}` で現在のフェーズと進捗を確認した

### 再インデックス Runbook の同期 (zero-downtime-reindex)

> 下記のいずれかを変更した PR は **必ず** [`docs/runbooks/reindex.md`](../docs/runbooks/reindex.md) を
> 同じ PR で更新してください。design.md の「イベントキー一覧」とも整合させます。

- [ ] `services/ingestion/reindex.py` の CLI 引数・サブコマンドを変更した場合、Runbook の該当コマンドブロックを更新した
- [ ] `shared/qdrant/` 以下のイベントキー (`reindex.*` / `search.*` / `ingestion.*`) を追加・変更・削除した場合、design.md の「イベントキー一覧」と Runbook の該当「期待ログ」を両方更新した
- [ ] `/healthz` / `/readyz` の応答仕様を変更した場合、Runbook のシナリオ 7 (健全性確認) を更新した
- [ ] `QDRANT_ALIAS` / `QDRANT_COLLECTION` 等の env を追加・変更した場合、`docker-compose.yml` / `.env.example` / README / Runbook を同期した

上記のいずれにも該当しない場合はこのセクションをスキップして構いません。
