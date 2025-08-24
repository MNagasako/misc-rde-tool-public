# 配布リポジトリ運用指示書

**重要**: このファイルは書き換えないこと

## 目的・役割

このリポジトリ（`C:\vscode\rde-public`）は、ARIM RDE Toolのバイナリ配布専用リポジトリです。

### 基本原則
- **開発禁止**: ソースコード編集・開発作業は一切行わない
- **配布専用**: コンパイル済みバイナリファイルの配布・リリース管理のみ
- **参照型運用**: 開発用リポジトリ（`C:\vscode\rde`）を読み込み専用で参照
- **同期維持**: 開発用リポジトリと同じバージョンを維持

## ファイル操作ルール

### 許可される操作
- **ドキュメント更新**: README.md, CHANGELOG.md, リリースノート等
- **設定ファイル編集**: .gitignore, ワークスペース設定等
- **バイナリコピー**: 開発用リポジトリからの配布用ファイル取得
- **ZIP作成**: 配布用圧縮ファイルの作成
- **リリース管理**: Git操作・GitHub Releases作成

### 禁止される操作
- **ソースコード編集**: .pyファイルの作成・編集
- **開発環境構築**: requirements.txt, setup.py等の作成
- **直接的バイナリ生成**: PyInstallerコマンドの実行
- **開発用リポジトリ変更**: 参照元の変更・影響

## リリース作業フロー

### 1. 情報収集・準備
```powershell
# 開発用リポジトリの最新情報を確認
cd C:\vscode\rde
git status
cat VERSION.txt
```

### 2. ドキュメント更新
- `VERSION.txt`: 開発用リポジトリから最新バージョン情報をコピー
- `README.md`: バージョン・リンク・機能説明を更新
- `docs/CHANGELOG.md`: 変更履歴を追記
- `docs/RELEASE_NOTES_v*.md`: 新バージョンのリリースノートを作成

### 3. バイナリファイル取得
```powershell
# 開発用リポジトリから最新バイナリをコピー
Copy-Item "C:\vscode\rde\dist\arim_rde_tool.exe" "C:\vscode\rde-public\dist\" -Force
Copy-Item "C:\vscode\rde\dist\input" "C:\vscode\rde-public\dist\" -Recurse -Force
```

### 4. 配布用ZIP作成
```powershell
cd C:\vscode\rde-public\dist
Compress-Archive -Path "arim_rde_tool.exe", "input", "output" -DestinationPath "arim_rde_tool_v1.13.2.zip" -Force
```

### 5. Git操作・リリース
```powershell
# ドキュメント更新をコミット
git add VERSION.txt docs/ README.md
git commit -m "Release v1.13.2: [変更内容の要約]"

# タグ作成・プッシュ
git tag -a v1.13.2 -m "ARIM RDE Tool v1.13.2"
git push origin main
git push origin v1.13.2

# GitHub Release作成
gh release create v1.13.2 "dist/arim_rde_tool_v1.13.2.zip" --title "ARIM RDE Tool v1.13.2" --notes-file "docs/RELEASE_NOTES_v1.13.2.md"
```

## バージョン管理

### バージョン体系
- **セマンティックバージョニング**: v1.13.2形式
- **開発用同期**: 開発用リポジトリと完全に同じバージョン番号
- **安定版維持**: 実運用推奨版として明示的に管理

### リリース種別
- **最新版**: 新機能・改善を含む最新リリース
- **安定版**: 実運用での使用に推奨されるバージョン
- **ホットフィックス**: 緊急バグ修正版

## ファイル構成・管理

### 配布ファイル（Git管理外）
```
dist/
├── arim_rde_tool.exe          # メイン実行ファイル（除外）
├── arim_rde_tool_v*.zip       # 配布用圧縮ファイル（除外）
├── input/                     # サンプル入力ファイル
└── output/                    # 出力フォルダ（空）
```

### ドキュメント（Git管理）
```
docs/
├── binary_build_notes.md      # 配布・使用方法
├── CHANGELOG.md               # 変更履歴
├── RELEASE_NOTES_v*.md        # リリースノート
└── instructions/              # 指示書群
    └── distribution.instructions.md  # この文書
```

### 設定ファイル
```
.gitignore                     # バイナリファイル除外設定
rde-public.code-workspace      # VS Code ワークスペース
.github/
└── copilot-instructions.md   # Copilot指示書
```

## トラブルシューティング

### よくある問題と対処

**バイナリファイルが見つからない**
- 開発用リポジトリでビルドが完了しているか確認
- パス指定が正しいか確認（`C:\vscode\rde\dist\arim_rde_tool.exe`）

**GitHub Releaseアップロードエラー**
- ファイルサイズ制限（2GB）を超えていないか確認
- GitHub CLI (`gh`) の認証状況を確認

**タグ競合エラー**
- 既存タグを削除してから再作成: `git tag -d v1.13.2`
- リモートタグも削除: `git push origin :refs/tags/v1.13.2`

## 注意事項

### セキュリティ
- **認証情報**: リポジトリに認証情報を含めない
- **プライベート情報**: 開発環境特有の情報を除外
- **バイナリ検証**: 配布前にウイルススキャンを実施

### 品質保証
- **動作確認**: 配布前にバイナリファイルの動作テストを実施
- **ドキュメント整合性**: バージョン情報・リンクの一貫性を確認
- **リリースノート**: 変更内容を正確に記載

### 継続運用
- **定期更新**: 開発用リポジトリとの同期を定期的に実施
- **アーカイブ管理**: 古いバージョンの適切な管理
- **ユーザーサポート**: GitHubイシューでのサポート対応
