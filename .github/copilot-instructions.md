<!--
Use this file to provide workspace-specific custom instructions to Copilot.
For more details, visit:
https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file
-->


# ARIM RDE Tool 公開配布リポジトリ

このリポジトリは、**ARIM事業 RDE→ARIMデータポータル移行ツール**の「バイナリ配布専用リポジトリ」です。
ソースコード編集は禁止、ドキュメント・設定ファイルのみ操作可能です。

---


## リポジトリ運用ルール（Copilot向け）

- **配布専用**: ソースコード編集は禁止。ドキュメント・設定ファイルのみ操作。
- **バイナリ管理**: 開発リポジトリ（`C:/vscode/rde`）でビルドしたバイナリを `dist/` にコピー。
- **リリース管理**: GitHub Releasesでバイナリ配布・バージョン管理。
- **仮想環境必須**: Python作業は必ず `.venv` を有効化。
- **ドキュメント整備**: 配布用README, CHANGELOG, RELEASE_NOTES等を最新版に保つ。

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


