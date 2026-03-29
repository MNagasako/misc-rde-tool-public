# ARIM RDE Tool（配布用リポジトリ）

[![Release](https://img.shields.io/github/v/release/MNagasako/misc-rde-tool-public)](https://github.com/MNagasako/misc-rde-tool-public/releases)
[![License: LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)

Windows向け配布版 **v2.5.42** のインストーラと利用者向けドキュメントを公開しています。

> [!NOTE]
> **[ARIM-RDE-TOOL 置き場](https://cuddly-stinger-40d.notion.site/ARIM-RDE-TOOL-2befc2cb5fc380f09d0dd4595b767f4d)**
> （こちらのほうが人力なので間違いが少ないです。更新頻度も高いです）

> [!IMPORTANT]
> 本ツールは個人開発の非公式ツールです。ARIM事業 / RDE / ARIMデータポータルの公式サポート対象ではありません。

## 1) 何ができるツールか（主要機能）

- RDEの操作補助（検索・取得・一覧確認）
- 基本情報の取得と一覧出力の支援
- データポータル連携（登録作業の支援）
- データポータルの主要操作ボタン整理と共有データセット選択UIの改善
- AI支援（説明文作成・補助、テンプレート選択、prompt assembly 切り替え）
- filtered_embed 辞書管理と AI 実行前の埋め込み方式切り替え
- ローカルLLM連携（Ollama / LM Studio の切り替え）
- 複数データセットや画像の一括処理
- AI提案系のデータセット絞り込み安定化

## 2) インストール方法

1. [Releases](https://github.com/MNagasako/misc-rde-tool-public/releases) から最新版インストーラを取得
2. `arim_rde_tool_setup.2.5.42.exe` を実行
3. 画面の案内に従ってインストール

初回起動時に `input/` と `output/` が自動作成されます。

## 3) 更新方法

1. [最新リリース](https://github.com/MNagasako/misc-rde-tool-public/releases/latest) を開く
2. 新しい `arim_rde_tool_setup.*.exe` をダウンロードして実行（上書き更新）
3. 必要に応じて整合確認
   - `latest.json` の `version` / `sha256`
   - `checksums.sha256` の該当行

## 4) 既知の注意点（最小限）

- サイト側仕様変更により動作へ影響が出る場合があります
- 重要データは事前にテスト用データで確認してください
- 認証情報はローカルPCに保存されるため、共用端末では取り扱いに注意してください

---

- 変更履歴: [docs/CHANGELOG.md](docs/CHANGELOG.md)
- ライセンス: [LICENSE](LICENSE)
- 第三者ライセンス: [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES)

