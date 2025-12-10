<!--
Use this file to provide workspace-specific custom instructions to Copilot.
For more details, visit:
https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file
-->


# ARIM RDE Tool 公開配布リポジトリ (v2.1.13)

このリポジトリは、**DICE/RDEシステム**及び**ARIMデータポータル**の統合UIとして動作し操作支援を行うPythonアプリケーションの「バイナリ配布専用リポジトリ」です。
ソースコード編集は禁止、ドキュメント・設定ファイルのみ操作可能です。

---

## バージョン管理・表記ルール

現在のバージョン: **2.1.13** (2025-12-02)

本リポジトリのバージョン情報は開発リポジトリ（`C:/vscode/rde`）の `src/config/common.py` の `REVISION` に基づいて統一管理されています。
配布用ドキュメント（README.md, VERSION.txt, CHANGELOG.md, RELEASE_NOTES等）も同じバージョン表記（例: 2.1.13/v2.1.13）に揃えています。

---

## リポジトリ運用ルール（Copilot向け）

- **配布専用（※方針変更）**: 本公開リポジトリはバイナリ配布が主目的です。ライセンスの変更（LGPLv3）及び第三者配布の方針変更に伴い、今後はソースコードを公開しない方針に移行します。ドキュメント・設定ファイルの更新は許可されますが、ソースコード編集・追加は行わないでください。
- **バイナリ管理**: 開発リポジトリ（`C:/vscode/rde`）でビルドしたバイナリを `dist/` にコピー。
- **リリース管理**: GitHub Releasesでバイナリ配布・バージョン管理。
- **仮想環境必須**: Python作業は必ず `.venv` を有効化。
- **ドキュメント整備**: 配布用README, CHANGELOG, RELEASE_NOTES等を最新版に保つ。
- **バージョン統一**: 全ドキュメントでバージョン表記を統一（VERSION.txt, README.md, CHANGELOG.md, RELEASE_NOTES等）

---


---

---


---

---


## 技術情報・重要ファイル

- **実行ファイル**: `dist/arim_rde_tool.exe`（PyInstaller --onefile）
- **配布形式**: ZIP圧縮（自己完結型、依存なし）
- **必要フォルダ**: `input/`, `output/`（初回起動時自動生成）
- **対応OS**: Windows 10/11 64bit
- **ドキュメント**: `README.md`, `docs/binary_build_notes.md`, `docs/CHANGELOG.md`, `docs/RELEASE_NOTES_v*.md`, `VERSION.txt`
- **サンプル**: `input-sample/`
- **設定**: `.gitignore`, `rde-public.code-workspace`

---

## 重要ファイル


