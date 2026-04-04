# RELEASE NOTES v2.5.46

- Release date: 2026-04-04
- Installer: `dist/arim_rde_tool_setup.2.5.46.exe`

## 主な更新点

- Basic Info の個別データ取得をバックグラウンドで進めながら、進捗確認と中止操作をしやすくしました。
- dataset / dataEntry / invoice の取得条件を整理し、新規・欠損・未成功分を優先して不要な再取得を抑制しました。
- invoice の失敗理由を記録し、既知の失敗を繰り返し再試行しないよう改善しました。
- Basic Info の段階表示と件数ベース進捗を強化し、処理状況を把握しやすくしました。

## 配布物整合

- latest.json を v2.5.46 のインストーラ情報に整合しました。
- checksums.sha256 に v2.5.46 の SHA256 を追加しました。
- README / VERSION.txt / CHANGELOG の表記を v2.5.46 に統一しました。

## チェックサム

- SHA256: `033605dbd7bb44fe447d49ea71b2e6dbc353c0ef89aabe1972a526e68193b3d1`