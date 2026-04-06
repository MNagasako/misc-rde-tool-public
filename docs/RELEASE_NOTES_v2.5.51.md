# RELEASE NOTES v2.5.51

- Release date: 2026-04-06
- Installer: `dist/arim_rde_tool_setup.2.5.51.exe`

## 主な更新点

- 更新履歴タブを VERSION.txt の履歴ベースに整理し、最新版の概要を安定して確認しやすくしました。
- サブグループ作成・更新時の確認表示で payload 側の userName を優先し、hidden 行が混ざる場合の表示ゆらぎを抑えました。
- 既存データセット候補の非同期読込中でも、表示済み候補の検索や選択を続けやすくしました。
- アプリ終了時の停止ガードとデータポータル一覧のキャンセル経路を整理し、終了時や中断時の挙動を安定化しました。

## 配布物整合

- latest.json を v2.5.51 のインストーラ情報に整合しました。
- checksums.sha256 に v2.5.51 の SHA256 を追加しました。
- README / VERSION.txt / CHANGELOG の表記を v2.5.51 に統一しました。

## チェックサム

- SHA256: `30c6ab28e7cfb9fc6ee1d63b8773bd7460960aae8faccfd89eee5b02cf704c58`