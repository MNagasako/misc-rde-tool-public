# RELEASE NOTES v2.1.15 (2025-12-03)

## 概要

- バージョンリビジョン更新（2.1.15）
- 公開配布ドキュメント更新（VERSION/README/CHANGELOG/本ファイル）
- GitHubタグ・リリース整備（インストーラー添付）
- 配布バイナリ: `dist/arim_rde_tool_setup.2.1.15.exe`

## 変更内容（配布版）

- ソースコードの変更はありません（公開配布リポジトリ方針に従い、ドキュメント・設定のみ更新）
- リリース手順を最新化（タグ発行→GitHub Release→バイナリ添付）

## 配布手順メモ（担当者向け）

1. バージョン更新
   - `VERSION.txt` を 2.1.15 に更新
   - `README.md` と `docs/CHANGELOG.md` を 2.1.15 に合わせて更新
2. タグ作成・プッシュ
   ```powershell
   git add .
   git commit -m "chore: bump version to 2.1.15 and update docs"
   git tag -a v2.1.15 -m "ARIM RDE Tool v2.1.15"
   git push origin main
   git push origin v2.1.15
   ```
3. GitHub Release作成
   - タイトル: `v2.1.15`
   - 本ファイルの内容を元に概要記載
   - 添付: `dist/arim_rde_tool_setup.2.1.15.exe`

## 既知事項

- インストーラー実行時にWindowsの警告が表示される場合があります。必要に応じて例外設定をご検討ください。
