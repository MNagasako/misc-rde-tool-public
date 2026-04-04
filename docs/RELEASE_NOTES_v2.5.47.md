# RELEASE NOTES v2.5.47

- Release date: 2026-04-04
- Installer: `dist/arim_rde_tool_setup.2.5.47.exe`

## 主な更新点

- 一覧系の CSV / XLSX 出力を共通化し、表の raw 値・hidden 列・cell widget 文字列を保持しやすく整理しました。
- Excel 読み込みを openpyxl ベースへ統一し、AI・報告書・設備・設定系の取り込み経路を整理しました。
- 報告書やデータ登録まわりの XLSX 出力を見直し、既存の出力機能を維持しながら依存関係を簡素化しました。
- pandas / xlsxwriter 依存を除去し、CSV / XLSX 周辺機能の回帰確認を強化しました。

## 配布物整合

- latest.json を v2.5.47 のインストーラ情報に整合しました。
- checksums.sha256 に v2.5.47 の SHA256 を追加しました。
- README / VERSION.txt / CHANGELOG の表記を v2.5.47 に統一しました。

## チェックサム

- SHA256: `b63c12db95729c67c9a7b23221f4a4f9754a6aacee82cdd3004bdc92899968ee`