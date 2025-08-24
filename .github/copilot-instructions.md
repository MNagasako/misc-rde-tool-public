<!--
Use this file to provide workspace-specific custom instructions to Copilot.
For more details, visit:
https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file
-->

# ARIM RDE Tool 公開配布リポジトリ (v1.13.2)

このリポジトリは、**ARIM事業 RDE→ARIMデータポータル移行ツール**のバイナリ配布専用リポジトリです。

---

## リポジトリ概要

- **配布目的**: コンパイル済みバイナリファイルの配布・リリース管理
- **開発リポジトリ**: `C:\vscode\rde` （読み込み専用参照）
- **バイナリソース**: 開発リポジトリでPyInstallerによりビルド
- **配布方法**: GitHub Releasesによるバイナリ配布
- **対象ユーザー**: ARIM事業実施機関・研究支援担当者

---

## 現在の配布状況（2025年8月24日）

- **最新版**: v1.13.2 - リファクタリング継続・フォーム機能分離・保守性向上
- **安定版**: v1.13.1 - 実運用推奨・継続的メンテナンス完了
- **配布形式**: Windows用自己完結型実行ファイル（ZIP圧縮）
- **ファイルサイズ**: 約151MB（v1.13.2）

---

## Copilotへの指示

このリポジトリでは、Copilotに対して以下のルールを優先的に適用します：

### **リポジトリ運用ルール**
- **開発用リポジトリ参照**: `C:\vscode\rde` から情報を取得・更新（読み込み専用）
- **バイナリ管理**: `.gitignore`でバイナリファイルを除外・GitHub Releasesで管理
- **ドキュメント整備**: 開発用リポジトリを参考に配布用ドキュメントを作成・更新
- **バージョン同期**: 開発用リポジトリと同じバージョンを維持

### **ファイル操作の重要ルール**
- **配布専用**: ソースコード編集は禁止・ドキュメント・設定ファイルのみ操作
- **バイナリコピー**: `C:\vscode\rde\dist\*` → `C:\vscode\rde-public\dist\*`
- **ZIP作成**: 配布用ZIPファイルは`dist/`フォルダ内で作成
- **リリース管理**: GitHub CLI (`gh release`) を使用してリリース作成

### **仮想環境の利用ルール**
- Python関連の作業は必ず `.venv` 仮想環境を有効化して実施すること
- コマンド例（Windows PowerShell）: `./.venv/Scripts/Activate`
- 主にドキュメント生成・リリース作業で使用

### **リリース作業フロー**
1. 開発用リポジトリから最新バイナリ・情報を取得
2. ドキュメント（README, CHANGELOG, RELEASE_NOTES）を更新
3. バイナリファイルをコピー・ZIP圧縮
4. Git commit・tag作成・push
5. GitHub Releaseを作成・ZIPファイルをアップロード

---

## 技術情報

### バイナリ配布形式
- **実行ファイル**: `arim_rde_tool.exe` （PyInstaller --onefile）
- **必要フォルダ**: `input/`, `output/` （初回起動時自動生成）
- **対応OS**: Windows 10/11 64bit
- **依存関係**: なし（自己完結型）

### リリース管理
- **GitHub Releases**: バイナリファイルのバージョン管理
- **タグ管理**: セマンティックバージョニング（v1.13.2形式）
- **安定版維持**: 実運用向け安定版の明示的管理

---

## 重要ファイル

### 配布関連
- `dist/arim_rde_tool.exe` — メイン実行ファイル
- `dist/arim_rde_tool_v*.zip` — 配布用圧縮ファイル
- `input-sample/` — サンプル入力ファイル群

### ドキュメント
- `README.md` — メイン説明・ダウンロードリンク
- `docs/binary_build_notes.md` — バイナリ配布・使用方法
- `docs/CHANGELOG.md` — 変更履歴
- `docs/RELEASE_NOTES_v*.md` — リリースノート
- `VERSION.txt` — バージョン情報

### 設定・管理
- `.gitignore` — バイナリファイル除外設定
- `rde-public.code-workspace` — VS Code ワークスペース設定
