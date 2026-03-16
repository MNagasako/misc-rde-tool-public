# RELEASE NOTES v2.5.36

- Release date: 2026-03-17
- Installer: `dist/arim_rde_tool_setup.2.5.36.exe`

## 主な更新点

- データ登録/タイルの一括登録タブで、データセット選択後に固有情報件数が存在していても「入力」切替でフォーム本体が展開されない不具合を改善しました。
- 固有情報フォーム本体とプレースホルダーの可視状態を整理し、summary 状態からの切替でも表示が崩れにくいようにしました。
- pytest / pre-build / PyInstaller のリリース導線更新を配布版へ反映しました。

## 配布物整合

- `latest.json` を v2.5.36 のインストーラ情報に整合しました。
- `checksums.sha256` に v2.5.36 の SHA256 を追加しました。
- README / VERSION.txt / CHANGELOG の表記を v2.5.36 に統一しました。

## チェックサム

- SHA256: `4644a0496061242938ce4e6170618377f8311e479d199524c2067ac09afaf9c0`