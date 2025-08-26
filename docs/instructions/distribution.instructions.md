git status
# バイナリ配布・運用手順

## 配布方法
- GitHub Releases から最新版バイナリ（ZIP形式）をダウンロード
- 配布用ZIPファイルを展開し、`arim_rde_tool.exe` を利用

## 運用フロー
1. 開発用リポジトリでバイナリビルド
2. 公開用リポジトリへバイナリ・ドキュメントをコピー
3. GitHub Releaseで配布・バージョン管理

## サポート
- ARIM事業実施機関・研究支援担当者向け
- 問い合わせは配布元リポジトリのIssueへ
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
