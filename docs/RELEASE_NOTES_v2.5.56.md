# RELEASE NOTES v2.5.56

- Release date: 2026-04-22
- Installer: `dist/arim_rde_tool_setup.2.5.56.exe`

## 主な更新点

- AI が追加取得する STRUCTURED ファイルの保存先を temp / dataFiles / dataFilesAI から選べるようにしました。
- 既存の dataFiles キャッシュや dataEntry キャッシュを再利用し、再取得を減らしながら AI 補助処理を継続しやすくしました。
- ファイル抽出設定の部分更新時も保存先設定を保持し、再設定時の取りこぼしを抑えました。

## 配布物整合

- latest.json を v2.5.56 のインストーラ情報に整合しました。
- checksums.sha256 に v2.5.56 の SHA256 を追加しました。

## チェックサム

- SHA256: `a9c369a5d6dc426d770e9bc9b5ed28e2d460b8dfaf470158d4366375fb0c6be8`