# RELEASE NOTES v2.5.55

- Release date: 2026-04-21
- Installer: `dist/arim_rde_tool_setup.2.5.55.exe`

## 主な更新点

- データポータルの managed CSV 取得で、旧 code/key 方式に加えて最新 filename を使う現行取得フローへ対応しました。
- managed CSV の新ヘッダ「アトリビュートタグ」「データセットURL」を既存列へ正規化し、旧データとの互換を維持しやすくしました。
- 一覧表示で managed 由来の冗長列を抑制し、マージ後の統一値を確認しやすくしました。

## 配布物整合

- latest.json を v2.5.55 のインストーラ情報に整合しました。
- checksums.sha256 に v2.5.55 の SHA256 を追加しました。

## チェックサム

- SHA256: `617e66dc3ccd8c5cfd2839a15c29f9dda1dccc6bc3026f22fd0f40b43859a12e`