# ARIM RDE Tool - Release Notes v2.2.2

**リリース日**: 2025年12月8日

---

## 概要

v2.2.2 はデータエントリー統計を複数画面で共有する仕組みと、STRUCTUREDファイルのJSON化コンテキストを追加したリリースです。`data_entry_summary` ヘルパーが dataEntry API のレスポンスを集計し、データセットタブとポータル編集ダイアログで同じ統計値を参照できるようになりました。さらに PortalEditDialog に共用合計２（非共有RAW/サムネイルを除いた値）を自動反映するボタンを追加し、ファイル数と総容量の入力ミスを防ぎます。

AI/AutoSetting まわりでは DatasetContextCollector が STRUCTUREDファイルをJSON形式でも保持するようになり、`{json_from_structured_files}` プレースホルダを AI テンプレート・データポータルプロンプトから直接利用できます。CSV/Excel の表構造を維持したままプロンプトへ渡せるため、AIレスポンスの精度と説明責任が向上します。

---

## 主要な改善点

### 📊 データエントリー統計の共通化
- `classes/dataset/util/data_entry_summary.py` を新設し、dataEntry JSON を解析してファイルタイプ別件数・サイズと shared1/2/3 の集計を一括管理。
- Dataset DataEntry Widget の統計ラベルと PortalEditDialog の自動入力ボタンが同じヘルパーを使用することで、画面間の整合性を保証。
- CSV/XLSX を JSON に正規化しつつ行列構造を保持するため、STRUCTUREDファイルの統計・コンテキストを再利用しやすくした。

### 🪄 データポータルのファイル統計自動入力
- PortalEditDialog に「ファイル数/全ファイルサイズを共用合計２から適用」するボタンを追加し、`get_shared2_stats()` の結果をそのままフォームへ反映。
- データエントリー情報が見つからない場合は API からの再取得を促すダイアログを表示し、Bearer Token を使って最新 JSON を保存した上で再計算。
- 適用前に件数と容量のプレビューを提示し、ユーザーが Yes/No を選択できるため誤適用を防止。

### 🧠 STRUCTUREDファイルのJSONコンテキスト
- DatasetContextCollector が `json_from_structured_files` キーを埋め込み、STRUCTUREDファイルの内容を JSON 文字列として AI コンテキストへ追加。
- AIExtensionBase と AutoSettingHelper が新プレースホルダを扱えるようになり、`{json_from_structured_files}` が必ず置換されることをテストで保証。
- CSV/Excel の読み取り時にテーブル形式のJSONへ変換し、AutoSetting/AIプロンプトからの二次利用や差分解析を容易化。

---

## テスト状況

- `pytest -q -k "data_entry_summary or dataset_context_structured_json or portal_file_stats_button"` : 追加した単体/ウィジェットテストが全て合格。
- `tests/unit/test_dataset_context_structured_json.py` : STRUCTURED JSON の生成/フォールバックを確認。
- `tests/unit/test_data_entry_summary.py` : shared2 集計が非共有RAW・サムネイルを除外することを検証。
- `tests/widgets/test_portal_file_stats_button.py` : PortalEditDialog の自動入力ボタンが正しい数値を適用することを確認。

---

## 既知の問題 / 注意事項

- PortalEditDialog の自動入力ボタンは最新の dataEntry JSON が `output/rde/data/dataEntry/` に存在することを前提とします。未取得の場合はダイアログの案内に従って API 取得を実行してください。
- STRUCTURED JSON はファイルサイズが大きい場合に長い文字列になるため、AI/AutoSetting プロンプトに渡す際は必要に応じて前処理を追加してください。

---

## アップグレード手順

1. v2.2.2 バイナリまたはソースを取得し、従来通り `.venv` を有効化して起動します。
2. 基本情報タブの「データエントリー取得」またはデータ取得2タブで dataEntry JSON を最新化し、`output/rde/data/dataEntry/{dataset_id}.json` が存在することを確認します。
3. PortalEditDialog を開き、新しい自動入力ボタンでファイル統計を適用できるか確認してください。必要に応じて API 再取得プロンプトに従って dataEntry JSON を更新します。
4. AIタブ/データポータルテンプレートで `{json_from_structured_files}` プレースホルダが期待通り置換されることをテストし、構造化JSONコンテキストを活用してください。
