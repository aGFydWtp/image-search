# Requirements Document

## Introduction
Firebase Storage上のアートワーク画像を自然言語で検索する既存のSearch API（`POST /api/artworks/search`）に対して、ブラウザから直感的に操作できる簡易的なシングルページアプリケーション（SPA）を構築する。バックエンドAPIは構築済みであり、本specではフロントエンドUIのみをスコープとする。

## Requirements

### Requirement 1: 検索入力
**Objective:** ユーザーとして、自然言語のテキストクエリを入力して検索を実行したい。直感的なキーワード入力だけで画像検索を開始できるようにするため。

#### Acceptance Criteria
1. The Search UI shall テキスト入力フィールドと検索ボタンを表示する
2. When ユーザーが検索ボタンをクリックする, the Search UI shall 入力テキストをクエリとして `POST /api/artworks/search` へリクエストを送信する
3. When ユーザーがテキスト入力フィールドでEnterキーを押す, the Search UI shall 検索ボタンクリックと同等の検索を実行する
4. While 検索クエリが空の状態, the Search UI shall 検索ボタンを無効化する
5. If 入力テキストが500文字を超える場合, the Search UI shall 入力を制限し、文字数上限を通知する

### Requirement 2: 検索結果表示
**Objective:** ユーザーとして、検索結果をサムネイル画像付きのグリッドレイアウトで一覧したい。視覚的に作品を比較・選択できるようにするため。

#### Acceptance Criteria
1. When 検索APIがレスポンスを返す, the Search UI shall 結果をサムネイル画像のグリッドレイアウトで表示する
2. The Search UI shall 各結果アイテムに作品タイトル、アーティスト名、サムネイル画像を表示する
3. When 検索結果が0件の場合, the Search UI shall 「該当する作品が見つかりませんでした」とメッセージを表示する
4. The Search UI shall 検索結果の件数を表示する

### Requirement 3: ヒット理由表示
**Objective:** ユーザーとして、各検索結果がなぜヒットしたかを確認したい。検索結果の妥当性を判断できるようにするため。

#### Acceptance Criteria
1. The Search UI shall 各結果アイテムに `match_reasons` をタグまたはバッジとして表示する
2. When ユーザーが結果アイテムにホバーまたはタップする, the Search UI shall スコアとヒット理由の詳細を表示する

### Requirement 4: 検索状態フィードバック
**Objective:** ユーザーとして、検索の処理状態を把握したい。システムが応答中であることを認識できるようにするため。

#### Acceptance Criteria
1. While 検索APIへのリクエストが処理中の状態, the Search UI shall ローディングインジケーターを表示する
2. While 検索APIへのリクエストが処理中の状態, the Search UI shall 検索ボタンを無効化する
3. If 検索APIがエラーレスポンスを返す場合, the Search UI shall エラーメッセージを表示し、再試行を促す
4. If 検索APIへの接続がタイムアウトした場合, the Search UI shall 「接続がタイムアウトしました」とメッセージを表示する

### Requirement 5: クエリ解析結果の表示
**Objective:** ユーザーとして、システムがクエリをどのように解釈したかを確認したい。意図した検索条件でフィルタリングされていることを確認するため。

#### Acceptance Criteria
1. When 検索が完了する, the Search UI shall `parsed_query` の内容（semantic_query、フィルタ条件）をユーザーに表示する
2. Where フィルタ条件（motif_tags, color_tags）が抽出されている場合, the Search UI shall フィルタタグを視覚的に区別して表示する

### Requirement 6: レスポンシブレイアウト
**Objective:** ユーザーとして、デスクトップおよびモバイルブラウザの両方で快適に検索したい。デバイスを問わず利用できるようにするため。

#### Acceptance Criteria
1. The Search UI shall デスクトップ（1024px以上）でグリッド列数を自動調整して表示する
2. The Search UI shall モバイル（768px未満）で1〜2列のグリッドレイアウトに切り替える
3. The Search UI shall 画像のアスペクト比を維持しながらサムネイルを表示する

### Requirement 7: SPAとしての基本構成
**Objective:** 開発者として、既存のDockerベースの開発環境に統合可能な軽量SPAを構築したい。追加の複雑なビルドインフラなしで運用するため。

#### Acceptance Criteria
1. The Search UI shall フレームワーク依存を最小限にした静的ファイル（HTML/CSS/JS）として構成する
2. The Search UI shall 既存のSearch APIサービスから静的ファイルとして配信可能な構成にする
3. The Search UI shall ページ遷移なしで検索と結果表示を同一画面で行う

