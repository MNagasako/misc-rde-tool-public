# ARIM RDE Tool - Release Notes v2.2.7

**リリース日**: 2025年12月17日

---

## 概要

v2.2.7 は、Windows 環境における pytest/pytest-qt 実行時の安定性を高めるための改善（テスト実行時のみのUI副作用抑制）と、リリースに伴うバージョン表記の更新を行ったリリースです。

---

## 主要な改善点

### 🧪 Windows / pytest-qt テスト安定化

- pytest実行時のみ、ネイティブUI操作（ダイアログ/可視化/強制processEvents等）を抑制し、0x8001010d 系の致命的クラッシュを回避
- テスト時のウィジェット生成・showイベント周辺の副作用を低減し、テストスイートの完走性を改善

### 📚 バージョン表記更新・ドキュメント整理

- VERSION.txt / README / CHANGELOG / リリースノート等の表記を v2.2.7 に統一
- v2.2.7 のリリースノート（本ファイル）を追加

---

## テスト状況

バージョンアップ時は、少なくとも以下の確認を推奨します。

- `./.venv/Scripts/python.exe -m pytest -q -k 'test_revision_sync'`
- `./.venv/Scripts/python.exe -m pytest -q`
