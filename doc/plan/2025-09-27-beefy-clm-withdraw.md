# Beefy CLM Vault Withdraw コスト表示 実装計画 (2025-09-27)

## 背景と目的
- 既存のワンテーブル比較に加えて、Beefy の LP（CLM Vault）からの withdraw コストを可視化し、ユーザーが単純送金との差分を把握できるようにする。
- 参考トランザクション：Avalanche C-Chain 上の BTC.b–WAVAX CLM Vault (Pharaoh) withdraw、ガス使用量 1,626,385。概算コストは baseFee 0.398 Gwei + priorityFee 1 Gwei 前提で約 0.00227 AVAX（約 $0.07 @ $30/AVAX）。

## スコープ
- 対象チェーン: 第一段階は Avalanche C-Chain の BTC.b–WAVAX CLM Vault。将来的に他チェーン／Vault 追加を見据えた拡張性を確保する。
- 表示対象: withdraw 時の gas limit、想定 gas price、ネイティブ建てコスト、および USD/JPY 換算（既存フィアット変換ロジックを再利用）。

## 想定 UI 変更
- `FeeTable` の各行に「LP解体ガス量」「LP解体ガス手数料」列を追加し、ネイティブ＋法定通貨換算を表示。
- CLM 対応 Vault が存在しないチェーンは `—` を表示。
- ステータスバッジには LP 解体のエラー／ノートも併記し、既存のチェーンメモとまとめて確認できるようにする。
- HTML ビューでは JPY/USD を同時取得し、クライアント側トグルでキャッシュ済みの値を切り替え。

## API 改修方針
1. **構成管理**
   - `api/app/config.py` に Beefy Vault 設定を追加（vault key, chain key, withdraw contract, strategy type など）。
   - CLM 固有値（例: 推奨 gas limit 1,626,385, 手動更新用メタ）を設定で保持。
2. **サービス層**
   - `api/app/services` に `beefy.py`（仮）を追加し、Vault 情報から withdraw コストを計算。
     - 初期版は固定 gas limit と現在のチェーン gas price（既存 `get_chain_fee` 結果の gas price）を組み合わせて算出。
     - フィアット換算は既存 `get_price_quotes` を再利用。
   - 将来的なダイナミック推定に備え、`eth_call` or `eth_estimateGas` の差し替えフックを意識した構造にする。
3. **エンドポイント**
   - `/fees/beefy` などの新規エンドポイントを追加し、`[{ vault, chain, gas_limit, native_fee, fiat_fee, notes }]` の JSON を返却。
   - 既存 `/fees/` レスポンスに `meta.extra_actions` のような形で埋め込む案もあるが、UI 実装を段階的に進めるため別エンドポイントを採用。
4. **キャッシュ**
   - `TTLCache` を流用し、チェーンガス価格の更新頻度と合わせて 30～60s キャッシュ。
   - Vault メタ情報は永続（手動更新時にコード変更）。

## フロントエンド改修方針
1. **状態管理**
   - `web/src/state` に新しい fetch フック（例: `useBeefyActions`）を追加し `/fees/beefy` を取得。
2. **型定義**
   - `web/src/types/api.ts` に Beefy アクション用インターフェースを追加。
3. **コンポーネント**
   - 既存 `FeeTable` の列・セルレンダリングを拡張し、LP 解体関連値を同じ行に描画。
   - ノート表示でガス算出根拠（例: "gasUsed 1,626,385 observed on 2025-09-27"）を併記する。
4. **スタイル**
   - `web/src/styles.css` にテーブルセクションのマージン／バッジ色調整を反映。

## テスト計画
- **API**: `api/tests/test_beefy_actions.py` を追加。
  - 固定 gas limit とモック gas price から期待コストが計算されること。
  - キャッシュ挙動とエラー時のフォールバック（RPC 失敗 → 既存チェーン価格が取れない場合のメッセージ）。
- **フロント**: `web/src/components/BeefyActionsTable.test.tsx` を追加。
  - API レスポンスをモックし、表に値が反映されること。
  - エラー時のメッセージ描画（“データ取得に失敗しました”など）。

## ログ・監視・オペレーション
- `dailyreport/` でガス推定値の変更履歴を残す運用ルールを明文化。
- ガス推定値更新手順:
  1. 標準ウォレットで対象 Vault から少額 withdraw。
  2. `eth_getTransactionReceipt` で `gasUsed` を取得。
  3. `doc/plan` にエビデンスを追記し、設定値を更新。

## スケジュール想定
1. バックエンド（設定・サービス・API テスト）: 0.5 日
2. フロントエンド（状態管理・UI・テスト）: 0.5 日
3. 結合確認（手動 E2E, ドキュメント更新）: 0.5 日
→ 合計 1.5 日を目安。

## 未決事項 / TODO
- 将来的に他チェーン CLM や非CLM Vault をどう扱うか整理（拡張フィールド設計）。
- USD/JPY 以外のフィアット対応要否。
- `/fees/` との統合タイミング（単一リクエストで済ませるか段階的に進めるか）。
- ガス価格ソースの冗長化（Infura 障害時の代替 RPC）。
