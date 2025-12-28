# リリースノート v2.1.24

**リリース日**: 2025年12月6日

---

## 主要な改善

### 🔄 サブグループ完全性チェックと自動再取得
- `groupOrgnizations/` と `subGroups/` の差分を検出し、欠損があれば必ず再取得ループを実行。
- 欠損IDをログに出力し、再取得対象を明示して復旧フローを自動化。

### 📊 サブグループ取得ループの詳細ログ
- 成功/失敗/スキップ件数を逐次記録し、force_download有無と処理時間もログ化。
- API呼び出し直前で個別ファイル有無を判定し、スキップ/再取得を決定する安全なループに整理。

### 🛠️ グループ選択ダイアログのUIスレッド固定
- 選択ダイアログをUIスレッドで同期実行するよう統一し、基本情報取得時のクラッシュを解消。
- `--force-dialog` やプロジェクト単一ケースでも安全にダイアログを表示。

### 🧰 その他
- データセットフィルタの既定プログラムを `all` に統一し、初期表示のフィルタ漏れを解消。
- 認証情報の暗号化ファイルを `encrypted_data` キーでラップし、既存フォーマットも後方互換で読み込み。

---

## テスト結果

- `./.venv/Scripts/python.exe -m pytest -q tests/unit/test_show_group_selection_if_needed.py` — 6 passed
- `./.venv/Scripts/python.exe -m pytest -q -k 'data_fetch2_dataset_combo_behavior or file_filter_widget_layout'` — 2 passed, 2 skipped, 678 deselected

---

## 互換性・注意点
- フォルダ完全性チェックは欠損検出時に再取得を強制するため、初回実行時は時間がかかる場合があります。
- グループ選択ダイアログはUIスレッド実行に固定されました。スクリプトから呼び出す場合もUIスレッドコンテキストで実行してください。
