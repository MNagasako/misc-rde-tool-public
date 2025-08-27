# ARIM RDE Tool

# ARIM RDE Tool 公開配布リポジトリ (v1.13.5)

このリポジトリは、ARIM事業 RDE→ARIMデータポータル移行ツールのバイナリ配布専用リポジトリです。

---

## リポジトリ概要

- **配布目的**: コンパイル済みバイナリファイルの配布・リリース管理
- **バイナリソース**: 開発リポジトリでPyInstallerによりビルド
- **配布方法**: GitHub Releasesによるバイナリ配布
- **対象ユーザー**: ARIM事業実施機関・研究支援担当者
- **最新版**: v1.13.5 - サブグループメンバー選択UI大幅改善・テーブル形式・ソート機能対応
- **配布形式**: Windows用自己完結型実行ファイル（ZIP圧縮）
- **ファイルサイズ**: 約142MB（v1.13.5）

## リポジトリ運用ルール
- **開発用リポジトリ参照**: `C:\vscode\rde` から情報取得・更新（読み込み専用）
- **ドキュメント整備**: 開発用リポジトリを参考に配布用ドキュメント作成・更新
- **バージョン同期**: 開発用リポジトリと同じバージョンを維持

- **配布専用**: ソースコード編集禁止・ドキュメント・設定ファイルのみ操作
- **ZIP作成**: 配布用ZIPファイルは`dist/`フォルダ内で作成
- **リリース管理**: GitHub CLI (`gh release`) を使用

- Python関連作業は必ず `.venv` 仮想環境を有効化して実施

---

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

### 最新版主な機能（v1.13.5）
- サブグループメンバー選択UI大幅改善（テーブル形式・ソート機能）
- 4列構成テーブル：名前・メール・OWNER・ASSISTANT列の整理された表示
- 列ヘッダークリックによる昇順・降順ソート（名前・メール列対応）
- 100人以上の大量メンバーでも快適操作
- 既存API・データ処理ロジックは完全互換

### リリース管理
- **GitHub Releases**: バイナリファイルのバージョン管理
- **タグ管理**: セマンティックバージョニング（v1.13.5形式）
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

## サブグループ管理機能
- **サブグループ新規作成**：メンバーと権限（OWNER/ASSISTANT）を指定、一括登録も可能
- **サブグループ修正**：既存グループの構成・課題番号・権限を変更可能

---

## 出力・可視化機能
- **XLSX出力**：ユーザー・サブグループ・データセット一覧をExcel出力（フィルタ対応）
- **リクエスト解析**：RDE APIリクエストを可視化、DevTools不要でデバッグ可能

---

## AI連携機能（試験実装）
### 概要
- OpenAI / Gemini / ローカルLLM対応
- 実験概要自動要約
- マテリアルインデックス（MI）自動推定
- データ品質評価、実験手法分析など複数のAI活用機能を提供


### 必要な準備
AI機能を利用するには、以下の設定が必要です：


# AI設定ファイルについて

AI機能を利用するための設定は、`input/ai_config.json` に記載します。今回提供いただいたファイルの内容を基に、README内に追記しました。

---

## `ai_config.json` 概要

```json
{
  "ai_providers": {
    "openai": {
      "enabled": true,
      "api_key": "API_KEY_FOR_OPENAI",
      "base_url": "https://api.openai.com/v1",
      "models": [
        "gpt-5", "gpt-5-mini", "gpt-5-nano",
        "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o4-mini-deep-research",
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"
      ],
      "default_model": "gpt-4o-mini"
    },
    "gemini": {
      "enabled": true,
      "api_key": "API_KEY_FOR_GEMINI",
      "base_url": "https://generativelanguage.googleapis.com/v1beta",
      "models": [
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-1.0-pro"
      ],
      "default_model": "gemini-2.0-flash"
    },
    "local_llm": {
      "enabled": true,
      "base_url": "http://localhost:11434/api/generate",
      "models": [
        "gemma3:1b", "gemma3:4b", "gemma3:12b", "gemma3:27b",
        "llama3.1:8b",
        "deepseek-r1:7b", "deepseek-r1:8b", "deepseek-r1:14b",
        "deepseek-coder-v2:16b",
        "qwen2.5:7b-instruct", "qwen2.5:14b-instruct",
        "qwen2.5-coder:7b-instruct",
        "gpt-oss:20b"
      ],
      "default_model": "gemma3:12b",
      "note": "Ollama等のローカルLLMサーバーが必要です。軽量版: gemma3:1b, 高性能版: gemma3:27b, コーディング: deepseek-coder-v2:16b, 推論: deepseek-r1シリーズ"
    }
  },
  "default_provider": "gemini",
  "timeout": 30,
  "max_tokens": 1000,
  "temperature": 0.7
}
```

### ポイント
- OpenAI / Gemini / ローカルLLMの3系統に対応
- 各プロバイダで利用可能なモデルを事前定義済み
- `default_provider` は `gemini` に設定されています
- `local_llm` 利用時は **Ollamaなどのローカルサーバー**が必要です

> **注意**: APIキーは必ず各自取得し、`ai_config.json` に記載してください。





#### **追加設定（既存データ解析用）**
以下を `input/ai/` 配下に配置してください：
- `prompts/` : AI解析用プロンプト群
- `quality_assessment.txt` → データ品質評価
- `dataset_explanation.txt` → データセット概要生成
- `experiment_method.txt` → 実験手法分析 
- `material_index.txt` → マテリアルインデックス推定


> **メモ**: `prompts` 内の各ファイルはユーザーが自由に書き換えてカスタマイズ可能です。


- `arim_exp.xlsx` : 実験情報定義ファイル
- `MI.json` : マテリアルインデックス定義
- `arim/converted.xlsx` : RDE用変換済みデータファイル

---

## ダウンロード
最新版バイナリは以下より取得できます：  
[https://github.com/MNagasako/misc-rde-tool-public/releases](https://github.com/MNagasako/misc-rde-tool-public/releases)

---

## 使用方法

### 1. 初回起動時の警告
Windowsのセキュリティ警告やアンチウイルスによりブロックされる場合は、必要に応じて例外設定をしてください。

<img width="532" height="498" alt="2025-07-31_18h22_53" src="https://github.com/user-attachments/assets/5117baeb-973c-4a7d-aed6-8f2d58400f26" />
<img width="532" height="498" alt="2025-07-31_18h23_02" src="https://github.com/user-attachments/assets/56e2ecce-466c-420e-ba84-95fc0eceacb5" />

---

### 2. ログイン
RDEアカウントでログインしてください。自動ログイン設定は `input/login.txt` に以下を記載します（DICEアカウントのみ対応）：

```txt
username(mail)
password
dice
```

---

### 3. 基本情報取得
<img width="1062" height="925" alt="2025-08-22_13h50_22" src="https://github.com/user-attachments/assets/bb481a4b-3585-409e-bad3-1941694ee20d" />

**基本情報**メニューから「基本情報取得（ALL または 検索）」と「invoice_schema取得」を実行します。

- RDEサーバー上のデータをローカルに一括取得し、検索機能を有効化します。
- 初回は時間がかかりますが、既存ファイルはスキップされます。
- 再取得したい場合は対象ファイルを削除後、再実行してください。

---

### 4. データ取得2（新方式）
<img width="1062" height="528" alt="2025-07-31_11h54_40" src="https://github.com/user-attachments/assets/cb5fd9dc-d093-47a5-9bd0-df88b75d0764" />

- ドロップダウンリストからデータセットを選択
- 「選択データセットのファイルリスト取得」ボタンで書誌情報と画像を一括取得

---

### 5. サブグループ作成・修正
<img width="1062" height="995" alt="2025-08-22_13h52_46" src="https://github.com/user-attachments/assets/6f4ecf71-22ab-4eea-87de-486e7f28934e" />

- グループメンバーと役割（OWNER/ASSISTANT）を設定
- `input/rde-member.txt` を使った自動選択にも対応
- 作成後は「基本情報取得」で情報を更新

<img width="1062" height="273" alt="2025-08-22_13h55_08" src="https://github.com/user-attachments/assets/09d32cbd-5cd4-477b-ab24-a305ab8f02be" />

サブグループ修正も同様に操作可能です。

---

### 6. データセット開設・修正
<img width="1062" height="528" alt="2025-07-31_10h51_01" src="https://github.com/user-attachments/assets/22f8d8f1-9f92-40e0-bab6-10e6cf0588cf" />
<img width="1062" height="710" alt="2025-08-22_14h15_23" src="https://github.com/user-attachments/assets/349caf93-a1d5-4c84-9a85-ee3c1e955f27" />

- サブグループを選択（補完検索対応）
- 課題番号を選択（登録済みである必要あり）
- データセット名、テンプレートを指定
- 広域シェア・匿名化オプションを選択
- 「データセット開設実行」をクリック

---

### 7. データ登録
<img width="1062" height="532" alt="2025-08-22_14h26_17" src="https://github.com/user-attachments/assets/9904b0d9-436e-4801-bf78-a0c2c42dbf15" />

- データセットを選択
- データ名・説明・試料情報を入力
- ファイルを添付
- 「データ登録」をクリック

---

### 8. AIテスト
<img width="1062" height="832" alt="2025-08-22_14h31_56" src="https://github.com/user-attachments/assets/c5dae4c6-b4cb-4341-93bd-45f0381d57bd" />

- 事前に `input/ai_config.json` および `input/ai/` ディレクトリを準備
- AIプロバイダ・モデルを選択
- 課題番号・実験データを選択
- 利用報告書データの使用有無を選択
- AI分析方法を選択し「AI分析実行」

<img width="1062" height="832" alt="2025-08-22_14h33_31" src="https://github.com/user-attachments/assets/1f58b255-b30d-4623-8f75-d7503e391e32" />

---

## 注意事項・免責
- このリポジトリはバイナリ配布専用
- 本ツールは**個人開発のため無保証**
- 再配布・転載は禁止

リリースページ：  
[https://github.com/MNagasako/misc-rde-tool-public/releases](https://github.com/MNagasako/misc-rde-tool-public/releases)

---

## ライセンス・問い合わせ
- ライセンス: 未定
- 制作: 東北大金研 長迫

## 関連ツール
- [https://github.com/MNagasako/BJB-PathFlattener](https://github.com/MNagasako/BJB-PathFlattener)
