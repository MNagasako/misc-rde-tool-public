# RELEASE NOTES v2.5.44

- Release date: 2026-04-01
- Installer: `dist/arim_rde_tool_setup.2.5.44.exe`

## 主な更新点

- 外部アクセスモニターを追加し、接続状態や通信状況を把握しやすくしました。
- TTLキャッシュ導入により、一覧や参照の再取得負荷を抑え、繰り返し操作を安定化しました。
- サブグループ完全性チェックを追加し、不足項目を事前確認しやすくしました。
- マスタデータの CSV / XLSX 出力に対応し、確認や共有を進めやすくしました。

## 配布物整合

- latest.json を v2.5.44 のインストーラ情報に整合しました。
- checksums.sha256 に v2.5.44 の SHA256 を追加しました。
- README / VERSION.txt / CHANGELOG の表記を v2.5.44 に統一しました。

## チェックサム

- SHA256: `5d2b4660345fa29e4cdd7cf91190aa7ca20f2895bb5d402b48e0c63e71bf1e22`