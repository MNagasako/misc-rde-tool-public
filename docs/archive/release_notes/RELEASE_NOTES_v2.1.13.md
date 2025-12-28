# Release Notes v2.1.13 (2025-12-02)

## 追加/変更点
- データセットタブ: 「🌐 ブラウザで表示」ボタン追加
  - 検索結果HTMLから `code` / `key` を抽出
  - 環境別URL（production/test）で公開ページを既定ブラウザ起動
- 装置・プロセス 自動設定: 設備IDからリンクタグ形式で登録
  - `output/arim-site/equipment/facilities_********_******.json` の最新を選択
  - 設備ID → code を検索し、`<a href="https://nanonet.go.jp/facility.php?mode=detail&code={code}">{ID}</a>` を生成
- ユーティリティ追加
  - `classes/utils/data_portal_public.py`: 公開ページURLビルダー（環境別）
  - `classes/utils/facility_link_helper.py`: 最新ファイル検索・設備ID抽出・code検索・アンカー生成
- 安定化
  - パス管理の誤インポート修正（`config.common` 参照に統一）

## テスト
- 単体テスト
  - `tests/unit/utils/test_facility_link_helper.py` 4件: 4 passed
  - `tests/unit/utils/test_data_portal_public.py` 3件: 3 passed
  - `tests/unit/test_dataset_upload_tab.py`（代表ケース実行）: 8 passed
- ウィジェットテスト
  - `tests/widgets/test_portal_edit_dialog_equipment_link.py`: 環境汚染のため `xfail`（仕様）

## 注意事項
- HTTPアクセスは `net.http_helpers` を使用（直接の requests 利用禁止）
- パス管理は `config.common` 経由で実装（CWD非依存）
- UI変更に伴うウィジェットテストはマーカー `@pytest.mark.widget` を付与
