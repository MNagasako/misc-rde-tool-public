# ARIM RDE Tool（配布用リポジトリ）

[![Release](https://img.shields.io/github/v/release/MNagasako/misc-rde-tool-public)](https://github.com/MNagasako/misc-rde-tool-public/releases)
[![License: LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)

Windows向け配布版 v2.5.45 のインストーラと利用者向けドキュメントを公開しています。

> [!NOTE]
> **[ARIM-RDE-TOOL 置き場](https://cuddly-stinger-40d.notion.site/ARIM-RDE-TOOL-2befc2cb5fc380f09d0dd4595b767f4d)**
> （こちらのほうが人力なので間違いが少ないです。更新頻度も高いです）

> [!IMPORTANT]
> 本ツールは個人開発の非公式ツールです。ARIM事業 / RDE / ARIMデータポータルの公式サポート対象ではありません。

## 1) 何ができるツールか（主要機能）

- RDE の検索、取得、一覧確認など日常操作の支援
- 基本情報の取得、マスタデータの CSV / XLSX 出力の支援
- データポータル連携による登録作業の補助とサブグループ完全性チェック
- データ取得2の初期表示軽量化と一括取得（DP）の待ち時間短縮
- 一括取得（DP）の進捗表示強化による処理状況の見える化
- 重い画面の遅延構築と終了時の実行中処理確認による操作安定化
- 外部アクセスモニターと TTL キャッシュによる状態確認と再操作の安定化
- AI支援、ローカルLLM連携、複数データセットや画像の一括処理

## 2) インストール方法

1. [Releases](https://github.com/MNagasako/misc-rde-tool-public/releases) から最新版インストーラを取得
2. arim_rde_tool_setup.2.5.45.exe を実行
3. 画面の案内に従ってインストール

初回起動時に input/ と output/ が自動作成されます。

## 3) 更新方法

1. [最新リリース](https://github.com/MNagasako/misc-rde-tool-public/releases/latest) を開く
2. 新しい arim_rde_tool_setup.*.exe をダウンロードして実行（上書き更新）
3. 必要に応じて整合確認
   - latest.json の version / sha256
   - checksums.sha256 の該当行

## 4) 既知の注意点（最小限）

- サイト側仕様変更により動作へ影響が出る場合があります
- 重要データは事前にテスト用データで確認してください
- 認証情報はローカル PC に保存されるため、共用端末では取り扱いに注意してください

---

- 変更履歴: [docs/CHANGELOG.md](docs/CHANGELOG.md)
- リリースノート: [docs/RELEASE_NOTES_v2.5.45.md](docs/RELEASE_NOTES_v2.5.45.md)
- ライセンス: [LICENSE](LICENSE)
- 第三者ライセンス: [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES)

