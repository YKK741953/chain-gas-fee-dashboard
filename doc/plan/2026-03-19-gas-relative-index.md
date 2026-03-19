# ガス代相対指数 実装計画 (2026-03-19)

## 背景と目的

- 現在のダッシュボードは、各チェーンの「今のガス代」を横比較する用途には十分だが、「そのチェーンにとって今が高いかどうか」は分かりにくい。
- このギャップを埋めるため、各チェーンの現在ガス代を過去 7 日の履歴と比較し、`1-10` の相対指数として表示する。
- 初期版では説明しやすさと運用安定性を優先し、`gas_price.gwei` を基準にした 7 日 percentile 指標を追加する。

## スコープ

- 対象チェーン: 既存の 6 チェーン
  - Ethereum
  - Polygon
  - Arbitrum
  - Optimism
  - Avalanche C-Chain
  - Linea
- 指標基準: `standard` モードで取得した `gas_price.gwei`
- 比較期間: 直近 7 日
- 出力形式: 各 `FeeRow` に `relative_index` を追加
- UI: 既存テーブルに 1 列追加

## スコープ外

- `precise` モード履歴の保存
- `native_fee` 基準の指数
- 24h / 30d など複数ウィンドウ対応
- sparkline グラフ
- 複数 API インスタンス前提の DB 運用

## 方針

### 指標定義

- 現在値 `current_gwei` を、同一チェーンの過去 7 日の履歴分布と比較する。
- percentile を求め、`1-10` に丸める。
- マッピングは以下とする。
  - `0% < p <= 10%`: 1
  - `10% < p <= 20%`: 2
  - ...
  - `90% < p <= 100%`: 10
- 補助情報として `percentile`, `samples`, `window`, `basis` も返す。

### 運用方針

- 履歴は API リクエスト時ではなく、API コンテナ内のバックグラウンド定期ジョブで収集する。
- 収集間隔の**初期値は 10 分**とする。
- 将来的に設定値で `5分 / 10分 / 15分` を切り替えられる余地は残すが、初期実装は 10 分固定でよい。
- 保存先は `shared/` 配下の SQLite とする。
- 正常値のみ保存し、`error`, `stale`, `gas_price_wei <= 0` は保存しない。

## データ設計

### 保存先

- ファイル候補: `shared/history/gas_history.sqlite3`

### テーブル案

`gas_price_history`

- `id` INTEGER PRIMARY KEY
- `chain_key` TEXT NOT NULL
- `observed_at` INTEGER NOT NULL
- `gas_price_wei` INTEGER NOT NULL
- `mode` TEXT NOT NULL
- `created_at` INTEGER NOT NULL

### インデックス案

- `idx_gas_price_history_chain_observed_at`
  - `(chain_key, observed_at)`

### 保持期間

- 表示上の集計窓は 7 日
- DB 保持は 90 日
- 古いデータはサンプラ実行時または日次で削除

## バックエンド実装

### 1. 設定追加

対象: [`api/app/config.py`](/home/ksmhome2025/Projects/chain-gas-fee-dashboard/api/app/config.py)

追加候補:

- `relative_index_enabled: bool = True`
- `relative_index_window_hours: int = 24 * 7`
- `relative_index_min_samples: int = 72`
- `relative_index_sample_interval_seconds: int = 600`
- `relative_index_retention_days: int = 90`
- `relative_index_db_path: Path = shared/history/gas_history.sqlite3`

### 2. 履歴保存サービス

新規候補:

- `api/app/services/history_store.py`

責務:

- SQLite 初期化
- 履歴 insert
- 7 日履歴 select
- 保持期限超過データ delete
- chain 単位の最新保存時刻取得

実装メモ:

- Python 標準 `sqlite3` で十分
- 競合を避けるため、書き込みは 1 プロセス内で直列化する
- API レスポンスのクリティカルパスから DB 書き込みを外す

### 3. 相対指数計算サービス

新規候補:

- `api/app/services/relative_index.py`

責務:

- 履歴配列から percentile を計算
- `1-10` へ変換
- ラベルを付与
- サンプル不足時に `null` または `warming_up` を返す

返却形:

```python
{
    "score": 8,
    "scale_max": 10,
    "label": "高い",
    "percentile": 0.82,
    "window": "7d",
    "samples": 1842,
    "basis": "gas_price_gwei",
}
```

### 4. サンプリングジョブ

対象: [`api/app/main.py`](/home/ksmhome2025/Projects/chain-gas-fee-dashboard/api/app/main.py)

実装方針:

- `startup` でバックグラウンドタスクを起動
- 10 分ごとに全チェーンの `standard` 値を取得
- 保存条件を満たすものだけ DB に書く
- 古い履歴を削除する
- `shutdown` でタスクを停止する

注意点:

- 既存 `get_chain_fee()` は TTL キャッシュを使うため、そのまま流用できる
- サンプラは `precise=False` 固定で呼ぶ
- 起動直後に 1 回即時実行してもよい
- 10 分間隔でも 7 日比較用途には十分な粒度を確保できる

### 5. `/fees/` レスポンス拡張

対象: [`api/app/routes/fees.py`](/home/ksmhome2025/Projects/chain-gas-fee-dashboard/api/app/routes/fees.py)

追加内容:

- 各 `row` に `relative_index` を付与
- 必要に応じて `relative_index_status` を付与
- `meta` に以下を追加
  - `relative_index_enabled`
  - `relative_index_window`
  - `relative_index_basis`

処理順:

1. 既存の `results` を取得
2. 各 row の `chain.key` と `gas_price.wei` を使って指数を計算
3. row に指数を付与
4. 既存レスポンスへ返す

### 6. 型更新

対象: [`web/src/types/api.ts`](/home/ksmhome2025/Projects/chain-gas-fee-dashboard/web/src/types/api.ts)

追加候補:

- `RelativeIndex`
- `relative_index?: RelativeIndex | null`
- `relative_index_status?: 'ok' | 'warming_up' | 'insufficient_data'`

## フロントエンド実装

### 1. テーブル列追加

対象: [`web/src/components/FeeTable.tsx`](/home/ksmhome2025/Projects/chain-gas-fee-dashboard/web/src/components/FeeTable.tsx)

表示案:

- `1W Relative`
- 表示値:
  - 通常: `8/10 高い`
  - warming up: `集計中`
  - データ無し: `—`

### 2. スタイル

対象候補:

- `web/src/styles.css`

初期版:

- 数値 + バッジのみ
- 色分け
  - 1-3 緑
  - 4-6 黄
  - 7-8 橙
  - 9-10 赤

### 3. 将来拡張しやすい UI ルール

- `percentile` は hover 用文言に使えるよう残す
- 初期版では sparkline は入れない
- 表示は短く、意味説明は tooltip または列ヘッダ補足へ逃がす

## エラー・例外方針

- サンプル不足時は `relative_index = null`
- 取得開始から十分な時間がたっていない場合は `relative_index_status = warming_up`
- DB 読み取り失敗時は指数なしで返し、既存のガス料金表示を壊さない
- サンプリング失敗はログに出すが、API 全体は落とさない

## テスト計画

### API

新規候補:

- `api/tests/test_relative_index.py`
- `api/tests/test_history_store.py`

観点:

- percentile から 10 段階へ正しく変換される
- サンプル不足時に `null` になる
- warming up 状態が正しく返る
- stale / error / zero 値を保存しない
- 保持期限を超えたデータが削除される

### 結合

- `/fees/` レスポンスに `relative_index` が付く
- 起動後、サンプラが SQLite を作成し書き込みできる
- DB が空でも `/fees/` が正常応答する

### フロント

対象候補:

- `web/src/components/FeeTable.test.tsx`

観点:

- `relative_index` がある時に列表示される
- `warming_up` が表示される
- `null` の時に `—` が表示される

## 実装ステップ

### Phase 1

- 設定値追加
- SQLite 履歴ストア追加
- percentile 計算サービス追加
- API コンテナ内バックグラウンドサンプラ追加
- `/fees/` レスポンスへ `relative_index` 追加
- フロントに 1 列追加
- API / フロントテスト追加

### Phase 2

- tooltip で `過去 7 日比 上位 xx%` を表示
- ラベル文言の改善
- 保持・削除処理の運用ログ整備

### Phase 3

- `native_fee` 基準への拡張
- 複数ウィンドウ対応
- グラフ表示追加

## 工数感

- バックエンド実装: 0.5-1.0 日
- フロント実装: 0.5 日
- テスト・結合確認: 0.5 日

合計の目安:

- 約 1.5-2.0 日

## リスクと判断

- 最大のリスクは「履歴が十分に育つまで価値が出ない」点
- 次点は SQLite ファイル運用だが、単一コンテナ運用なら許容範囲
- 初回から複雑化せず、`standard + 5分 + 7日 + SQLite` に固定すれば実装も運用も十分現実的
- 初回から複雑化せず、`standard + 10分 + 7日 + SQLite` に固定すれば実装も運用も十分現実的

## 先に決めておくこと

1. 列名を `1W Relative` / `混雑度` のどちらにするか
2. ラベルを日本語で返すか、UI 側で変換するか
3. `warming_up` の閾値を「24時間」か「72サンプル」どちら優先にするか
4. 起動直後にサンプラを 1 回即実行するか
