# ARIM RDE Tool v2.1.14 リリースノート

**リリース日**: 2025年12月2日

---

## 📋 新機能・改善

### 1. データポータル自動設定ダイアログ改善

#### 情報源選択に説明文表示を追加
- 全ての自動設定ダイアログ（重要技術領域・横断技術領域・装置・プロセス）に説明文を表示
- ダイアログの機能と情報源（報告書/AI）を明示してユーザビリティ向上
- `AutoSettingDialog` に `description` パラメータを追加
- 自動説明生成機能 `_generate_description()` 実装

**説明文例:**
- 重要技術領域: "報告書またはAIから重要技術領域の候補を取得し、主・副を設定します。"
- 横断技術領域: "報告書から横断技術領域の候補を取得し、主・副を設定します。"
- 装置・プロセス: "報告書から利用した設備の候補を取得し、選択的置換ダイアログで適用します。"

#### 装置・プロセス自動設定の2段階フロー実装
- **第1段階**: `AutoSettingDialog` で情報源選択と候補取得
- **第2段階**: `SelectiveReplacementDialog` で選択的置換
- 重要技術領域・横断技術領域と統一されたUX提供
- 候補取得時のプログレスダイアログを `AutoSettingDialog` 内に集約

**修正ファイル:**
- `src/classes/data_portal/ui/auto_setting_dialog.py`
  - 説明ラベル追加
  - 装置・プロセスリスト形式の表示対応（`_display_candidates()`）
  - 適用確認ダイアログの装置・プロセス対応（`_on_apply()`）

- `src/classes/data_portal/ui/portal_edit_dialog.py`
  - `_on_auto_set_equipment()` を2段階フロー方式に変更

### 2. 設備リンク名称付与機能

#### 設備ID + 設備名の形式に改善
従来の設備IDのみのリンクから、設備名を含む形式に改善しました。

**変更前:**
```html
<a href="https://nanonet.go.jp/facility.php?mode=detail&code=5">NM-005</a>
```

**変更後:**
```html
<a href="https://nanonet.go.jp/facility.php?mode=detail&code=5">NM-005:液中原子間力顕微鏡 (AFM)</a>
```

#### 新規機能
- `lookup_facility_name_by_equipment_id()`: 設備IDから設備名称を取得
- `build_equipment_anchor_with_name()`: 設備ID+設備名のアンカータグを生成

**修正ファイル:**
- `src/classes/utils/facility_link_helper.py`
  - 設備名取得関数追加
  - 名称付きアンカー生成関数追加

- `src/classes/data_portal/ui/portal_edit_dialog.py`
  - `_on_auto_set_equipment()`: リンク化コールバックを名称付きに変更
  - バッチ設定処理: 名称付きリンク生成に変更
  - `_on_facility_link_batch()`: 一括リンク化も名称付きに対応

### 3. テスト追加

#### AutoSettingDialog用テスト（5件）
新規テストファイル: `tests/unit/data_portal/test_000_auto_setting_dialog.py`

- `test_auto_setting_dialog_init_with_description`: 説明文付き初期化テスト
- `test_auto_setting_dialog_auto_description_generation`: 自動説明生成テスト
- `test_auto_setting_dialog_equipment_list_display`: 装置・プロセスリスト表示テスト
- `test_auto_setting_dialog_main_sub_display`: 主・副形式表示テスト
- `test_auto_setting_dialog_apply_confirmation_equipment`: 適用確認ダイアログテスト

**注意:** Qt環境汚染対策として `@pytest.mark.widget` + `@pytest.mark.xfail` を設定

#### facility_link_helper用テスト拡張
既存テストファイル: `tests/unit/utils/test_facility_link_helper.py`

- `test_lookup_facility_name_by_equipment_id`: 設備名取得テスト（新規）
- `test_build_equipment_anchor_with_name`: 名称付きアンカー生成テスト（新規）

#### portal_edit_dialog_facility_link用テスト更新
既存テストファイル: `tests/unit/data_portal/test_000_portal_edit_dialog_facility_link.py`

- テストデータに設備名称フィールドを追加
- アサーションを名称付きリンク形式に更新

### 4. ファイル名変更
テスト実行順序の最適化のため、以下のファイルをリネーム:

- `test_auto_setting_dialog.py` → `test_000_auto_setting_dialog.py`
- `test_portal_edit_dialog_facility_link.py` → `test_000_portal_edit_dialog_facility_link.py`
- `test_selective_replacement_dialog.py` (widgets) → `test_selective_replacement_dialog_widget.py`

---

## 🧪 テスト結果

### 単体実行
- **data_portal全テスト**: 15件中15件成功 (10 passed, 5 xpassed)
- **facility_link_helper**: 6件中6件成功
- **全テスト実行**: 84 passed, 68 skipped, 5 xfailed

### テスト詳細
- **新規追加テスト**: 7件（AutoSettingDialog: 5件、facility_link_helper: 2件）
- **更新テスト**: 3件（portal_edit_dialog_facility_link）
- **Qt環境汚染対策**: widgetマーカー + xfail による安定化

---

## 📝 技術的詳細

### AutoSettingDialogの拡張性向上

#### 汎用的な候補表示
```python
# 主・副形式（重要技術領域・横断技術領域）
{"main": "ナノテクノロジー・材料", "sub": "エネルギー"}

# リスト形式（装置・プロセス）
{"equipment": ["NM-005", "ST-001", "AB-123"], "text": "NM-005\nST-001\nAB-123"}
```

#### 適用確認ダイアログの分岐
```python
if "equipment" in self.candidates:
    # 装置・プロセス形式: 件数とプレビュー表示
    preview = "\n".join(equipment_list[:5])
    if count > 5:
        preview += f"\n... 他 {count - 5}件"
else:
    # 主・副形式
    "主: {main}\n副: {sub}"
```

### facility_link_helperの機能拡張

#### 設備名取得
```python
def lookup_facility_name_by_equipment_id(json_path: Path, equipment_id: str) -> Optional[str]:
    """設備IDから設備名称を取得"""
    # facilities_*.json から "設備名称" フィールドを取得
    return name  # 例: "液中原子間力顕微鏡 (AFM)"
```

#### 名称付きアンカー生成
```python
def build_equipment_anchor_with_name(code: str, equipment_id: str, equipment_name: str) -> str:
    """設備ID+設備名のアンカータグ生成"""
    return f'<a href="...">NM-005:液中原子間力顕微鏡 (AFM)</a>'
```

---

## 🔄 下位互換性

### 完全互換
- 既存の `build_equipment_anchor()` は保持（ID のみのリンク生成）
- 新規 `build_equipment_anchor_with_name()` を追加
- 既存のデータポータル修正機能は影響なし

### データフォーマット
- `facilities_*.json` の "設備名称" フィールドを使用
- フィールドが存在しない場合は従来通りIDのみで動作

---

## 📦 影響範囲

### 変更されたファイル
1. `src/config/common.py` - REVISION更新
2. `VERSION.txt` - バージョン履歴追加
3. `README.md` - 最新機能セクション更新
4. `src/classes/data_portal/ui/auto_setting_dialog.py` - 説明文・装置対応
5. `src/classes/data_portal/ui/portal_edit_dialog.py` - 2段階フロー・名称付きリンク
6. `src/classes/utils/facility_link_helper.py` - 設備名取得・名称付きアンカー
7. `tests/unit/data_portal/test_000_auto_setting_dialog.py` - 新規テスト
8. `tests/unit/utils/test_facility_link_helper.py` - テスト拡張
9. `tests/unit/data_portal/test_000_portal_edit_dialog_facility_link.py` - テスト更新

### 新規追加ファイル
- `tests/unit/data_portal/test_000_auto_setting_dialog.py`
- `RELEASE_NOTES_v2.1.14.md`

### リネームファイル
- `test_selective_replacement_dialog.py` → `test_selective_replacement_dialog_widget.py`

---

## 🚀 今後の展開

### 短期計画
- データポータル修正機能のさらなるUI/UX改善
- 自動設定機能のAI推定対応強化
- テストカバレッジの継続的向上

### 中期計画
- データエントリー機能の拡張
- バッチ処理機能の改善
- パフォーマンス最適化

---

## 📞 サポート

問題が発生した場合は、以下の情報を含めて報告してください:

1. バージョン情報: v2.1.14
2. 実行環境（OS、Python バージョン）
3. エラーメッセージまたは問題の詳細
4. 再現手順

---

**変更履歴**

| 日付 | バージョン | 変更内容 |
|------|-----------|---------|
| 2025-12-02 | v2.1.14 | データポータル自動設定改善・設備リンク名称付与 |
