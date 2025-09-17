<img width="1062" height="1004" alt="2025-09-17_11h16_05" src="https://github.com/user-attachments/assets/7bfa5101-3269-45d1-997e-7a6da7e95e3b" /># ARIM RDE Tool v1.17.4

---

## 概要

**ARIM RDE Tool**は、DICE/RDEシステムからARIMデータポータルへのデータ移行・管理を支援するWindows用ツールです。GUI操作でサブグループ・データセット・AI活用など多彩な機能を提供し、研究データの効率的な運用を実現します。

| バージョン | リリース日 | 主な更新内容 |
|:---:|:---:|:---|
| v1.17.4 | 2025-09-17 | 安定性向上・細かなバグ修正・ドキュメント整理 |
| v1.17.3 | 2025-09-16 | AI機能拡張・UI改善・エラーハンドリング強化 |

---

## 目次

- [概要](#概要)
- [主な特徴](#主な特徴)
- [動作環境](#動作環境)
- [インストール・使い方](#インストール使い方)
- [既知の不具合・注意事項](#既知の不具合注意事項)
- [サポート・報告方法](#サポート報告方法)
- [ライセンス](#ライセンス)
- [関連リンク](#関連リンク)

---

## 主な特徴

- サブグループ・データセットの一括管理・編集
- AIによる説明文生成・品質評価（OpenAI/Gemini/ローカルLLM対応）
- RDE情報の一括取得・XLSX出力
- 柔軟なフィルタ・検索・補完機能
- 直感的なGUI・多機能タブ構成
- 設定ファイル（JSON/Excel）による柔軟なカスタマイズ

---

## 動作環境

- Windows 10/11 64bit
- Python 3.10以降（バイナリ配布版はPython不要）
- 必要フォルダ：`input/`, `output/`（初回起動時自動生成）

---

## インストール・使い方

1. [GitHub Releases](https://github.com/MNagasako/misc-rde-tool-public/releases)から最新版ZIPをダウンロード
2. ZIPを展開し、`arim_rde_tool.exe`を実行
3. `input/`フォルダに設定ファイルやデータを配置
4. GUI画面から各種操作を実施

詳細な手順・サンプルは`input-sample/`や`docs/`フォルダを参照してください。

---

## 既知の不具合・注意事項

> ⚠️ ディスプレイサイズや解像度によって、ウインドウや文字サイズが意図せず変化する場合があります。
> 開発時の環境（特定の解像度・DPI設定）でのみ動作検証を行っています。他環境では文字が小さすぎる・ボタンが押せない等の不具合が発生する可能性があります。
> 不具合がございましたら「ご利用環境（OS・解像度・DPI等）」とともにご報告ください。スクリーンショットも添付いただけると迅速な対応が可能です。

---

## サポート・報告方法

- 不具合・要望は[GitHub Issues](https://github.com/MNagasako/misc-rde-tool-public/issues)またはリリースページからご連絡ください。
- ご利用方法・技術的な質問も歓迎します。

---

## ライセンス

本ツールはGPLv3ライセンスで公開しています。
詳細は`LICENSE`ファイルをご参照ください。

---

## 関連リンク

- [最新版バイナリ・リリースノート](https://github.com/MNagasako/misc-rde-tool-public/releases)
- [CHANGELOG（詳細な更新履歴）](docs/CHANGELOG.md)
- [AI機能ガイド](docs/AI_FEATURE_GUIDE.md)
- [バイナリビルド手順](docs/binary_build_notes.md)

---

---

## 概要・注意事項

本ソフトウェアは、ARIM-RDEサイトの操作を支援するツールです。
ご利用には、RDEサイトのアカウントが必要です。

（重要）本ドキュメントにはAIによる自動生成部分が多く含まれます。自動生成された文章には誤りが含まれる場合がございますので、内容を鵜呑みにせずご注意ください。また、配布バイナリは当方環境で動作確認済みですが、他環境での動作は保証いたしかねます。時間ができ次第、整理予定です。

> **RDEリンク機能ご利用時の注意**
> RDEリンク機能を使用する場合は、予めブラウザ（Chrome推奨）側でもRDEサイトへログインを済ませておく必要があります。
> ※Windows/Chromeのみ動作確認済み。他ブラウザ・OSはご要望があれば検証対応します。

---

## 主な独自機能
- サブグループ：Roleによるフィルタ表示、試料情報抽出、RDEリンク
- データセット：タクソノミーキービルダー、TAGビルダー、関連データセットの簡易検索・設定
- データ登録：データセットの簡易指定、補完フィルタ
- RDE情報取得（基本情報）：一括取得、XLSX出力
- AIテスト機能

## 主な非対応機能
- 削除系APIリクエスト（安全性を考慮し未実装。編集ページへのリンクからRDEサイト上で削除）

## 主な未対応機能
- データカタログの作成・編集
- 送り状編集（対応予定）
- 添付ファイル削除
- CSVインポートによるグループメンバー一括置換
- 関連試料設定（対応予定）

## 開発中・ToDo
- AI機能の継続的拡張（プロバイダ追加・プロンプトカスタマイズ性向上）
- Data Fetch 2のフィルタUI/ロジック最終調整
- PyQtのライセンス問題があるため、将来的にPySideへの移行を検討中です。

---

> ※本章の内容が最新です。以降のマニュアル的記載には一部古い内容が含まれる場合がございます。



## ダウンロード

最新版バイナリは、以下より取得いただけます。  
[https://github.com/MNagasako/misc-rde-tool-public/releases](https://github.com/MNagasako/misc-rde-tool-public/releases)


---

## ご利用方法

> ※本章以降の手順・画面例は一部古い内容が含まれる場合がございます。最新の機能・仕様は冒頭「現在の機能と拡張について」をご参照ください。

### 1. データ取得の事前準備（必須）

本ツールでは大部分のデータを予めRDE側から取得して動作します。ご利用前に、
  - 基本情報メニューから「基本情報取得（ALL または 検索）」
  - 「サンプル情報強制取得」
  - 「invoice_schema取得」
を必ず実行してください。

初回はかなり時間がかかります（20～30分かかる場合もあります）。
短縮したい場合は「基本情報取得（検索）」を利用し、検索用キーワード（例：課題番号のプリフィックス等）で絞り込んでください。

既存データがある場合はスキップされます。

---

### 2. バージョンアップ時の注意

アプリのバージョンを更新した場合は、INPUT・OUTPUTフォルダはそのままにしておき、実行ファイル（EXE）のみ入れ替えてください。
実行ファイルのファイル名は変更しても動作します。旧バージョンを残したい場合は適当にリネームして同じフォルダに入れておいても問題ありません。

バージョン更新によって必要となる情報が追加されたり保存形式が変わる場合があります。新しいバージョンに変更した際は、再度上記「データ取得の事前準備」を実施してください。

---

### 3. 初回起動時の警告

Windowsのセキュリティ警告やアンチウイルスによりブロックされる場合は、必要に応じて例外設定を行ってください。

<img width="532" height="498" alt="2025-07-31_18h22_53" src="https://github.com/user-attachments/assets/5117baeb-973c-4a7d-aed6-8f2d58400f26" />
<img width="532" height="498" alt="2025-07-31_18h23_02" src="https://github.com/user-attachments/assets/56e2ecce-466c-420e-ba84-95fc0eceacb5" />

---

### 4. 設定

<img width="1062" height="1004" alt="2025-09-17_11h16_05" src="https://github.com/user-attachments/assets/0991e17a-62aa-461d-bc64-8983c694b384" />
<img width="1062" height="1004" alt="2025-09-17_11h17_17" src="https://github.com/user-attachments/assets/65baed9c-e52e-4cb6-9999-5ac6ad100267" />

・必要な場合は設定メニューでプロキシの設定を行ってください。通常のブラウザでインターネットアクセスできていれば本ツールも使用可能です。（認証が必要な場合は対応していません。）

> **自動ログイン設定について**
> - 「暗号化ファイル」または「OSキーチェーン」への保存を推奨（設定メニューで選択可能）。
> - `input/login.txt` への平文保存は**非推奨**です。やむを得ず利用される場合は、下記の形式でご記載ください（DICEアカウントのみ対応）。
>   ```txt
>   username(mail)
>   password
>   dice
>   ```
> - login.txt利用時は毎回警告が表示されます。できるだけ安全な保存方法へ移行してください。

---

### 5. ログイン

RDEアカウントでログインしてください。

・本ツールではRDEサイトへのAPIアクセスを行う為、使用にはログインが必要です。
・自動ログインを設定している場合は、RDEサイトのログイン後のページ(データセット一覧)が表示されます。
・ログインメニューを選択した際に、RDEのログインメニューが表示される場合は未ログインなのでログインしてください。
・ブラウザエラー表示の場合は、自動ログインの設定が間違っているため、ログイン情報を再設定するか、自動ログインを無効化してアプリを再起動してください。


### 6. 基本情報取得
<img width="1062" height="925" alt="2025-08-22_13h50_22" src="https://github.com/user-attachments/assets/bb481a4b-3585-409e-bad3-1941694ee20d" />

**基本情報**メニューから「基本情報取得（ALL または 検索）」「invoice_schema取得」及び「サンプル情報強制取得」を実行してください。

- RDEサーバー上のデータをローカルに一括取得し、検索機能を有効化します。
- 初回は時間を要します（10-20分程度？）が、既存ファイルはスキップされます。
- 強制再取得が必要は、対象ファイルを削除後、再度実行してください。

---

### 7. データ取得2（新方式）
<img width="1062" height="632" alt="2025-09-17_11h08_48" src="https://github.com/user-attachments/assets/4d1ff881-9c61-4673-acd3-a22f1ca4b1b3" />
<img width="1062" height="632" alt="2025-09-17_11h08_58" src="https://github.com/user-attachments/assets/6865cdfe-dd10-400e-8c0d-30597bb85712" />

-　データ取得タブ　のドロップダウンリストからデータセットを選択してください。（補完検索可）
- 「選択データセットのファイルを一括取得」ボタンで、書誌情報および画像を一括取得できます。
- データセットリストは広域シェア設定、ログイン中のユーザーのロール（権限）､課題番号で絞り込みできます。
- ファイルフィルタタブではダウンロードするファイルの属性・拡張子・ファイルサイズ・ファイル名・ダウンロード上限ファイル数などを設定出来ます。（設定してからデータ取得タブで一括取得を行ってください）

---

### 8 サブグループ　（研究グループ）
<img width="1062" height="1004" alt="2025-09-17_11h26_44" src="https://github.com/user-attachments/assets/1c1a5902-7bae-43ab-8c75-36ad7a6d8c6c" />
<img width="1062" height="1004" alt="2025-09-17_11h26_54" src="https://github.com/user-attachments/assets/9ddfe44b-0726-439a-9f3a-7b13d5783dc4" />

#### サブグループ新規作成

1. **グループに追加するメンバーの役割を設定してください。**
  - メンバーリストには、ログイン中ユーザーが所属するサブグループのメンバーが含まれます。
  - `input/rde-member.txt` でメンバーの役割のデフォルト値を指定できます。
  - リストにないメンバーを追加する場合は、メールアドレスを入力し「ユーザー追加」をクリックしてください（RDEに登録済みのユーザーであればリストに追加されます）。

2. **グループ名、説明、課題番号、研究資金番号を設定します。**

3. **「作成」ボタンをクリックします。**
  - ※「一括作成」ボタンは現在利用できません（押すとアプリがクラッシュします）。

---

#### サブグループ修正

1. **サブグループ選択ドロップダウンリストから修正対象のサブグループ（研究グループ）を選択します。**
  - 補完検索が可能です。
  - 表示フィルタでリスト内エントリーの絞り込みもできます。

2. **サブグループの内容を変更する場合は「サブグループ更新」をクリックします。**

  - **RDEサブグループページを開く**  
    選択中のサブグループのページをRDE上で開きます（事前にブラウザでRDEサイトへログインしておいてください）。

  - **関連試料抽出ボタン**  
    選択中サブグループに属する試料一覧を表示し、クリックでRDEのサンプルページを開きます。  
    ※試料情報の編集や削除はRDEサイト上での操作が便利です。

--

### 9. データセット開設・修正
<img width="1062" height="528" alt="2025-07-31_10h51_01" src="https://github.com/user-attachments/assets/22f8d8f1-9f92-40e0-bab6-10e6cf0588cf" />
<img width="1062" height="710" alt="2025-08-22_14h15_23" src="https://github.com/user-attachments/assets/349caf93-a1d5-4c84-9a85-ee3c1e955f27" />

- サブグループを選択（補完検索対応）
- 課題番号を選択（登録済みである必要あり）
- データセット名、テンプレートを指定
- 広域シェア・匿名化オプションを選択
- 「データセット開設実行」をクリック

---

### 10. データ登録
<img width="1062" height="532" alt="2025-08-22_14h26_17" src="https://github.com/user-attachments/assets/9904b0d9-436e-4801-bf78-a0c2c42dbf15" />

- データセットを選択
- データ名・説明・試料情報を入力
- ファイルを添付
- 「データ登録」をクリック

---

### 11. AIテスト
<img width="1062" height="832" alt="2025-08-22_14h31_56" src="https://github.com/user-attachments/assets/c5dae4c6-b4cb-4341-93bd-45f0381d57bd" />

- 事前に `input/ai_config.json` および `input/ai/` ディレクトリを準備
- AIプロバイダ・モデルを選択
- 課題番号・実験データを選択
- 利用報告書データの使用有無を選択
- AI分析方法を選択し「AI分析実行」

<img width="1062" height="832" alt="2025-08-22_14h33_31" src="https://github.com/user-attachments/assets/1f58b255-b30d-4623-8f75-d7503e391e32" />

---




## バイナリ化方法（開発用リポジトリでの手順）

1. **仮想環境の有効化と依存モジュールのインストール**
  ```powershell
  # PowerShell例
  cd C:\vscode\rde
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```

2. **PyInstallerによるバイナリ化**
  ```powershell
  pyinstaller --exclude-module pytest --noconsole --onefile --icon "src/image/icon/icon1.ico" --add-data "src/image;image" --add-data "config;config" --add-data "src/js_templates;js_templates" src/arim_rde_tool.py
  ```

- バイナリ（`dist/arim_rde_tool.exe`）が生成されます。

---

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

> **注意**: APIキーは各自取得し、`ai_config.json` に記載してください。





#### **追加設定（既存データ解析用）**
以下を `input/ai/` 配下に配置してください：
- `prompts/` : AI解析用プロンプト群
- `quality_assessment.txt` → データ品質評価
- `dataset_explanation.txt` → データセット概要生成
- `experiment_method.txt` → 実験手法分析 
- `material_index.txt` → マテリアルインデックス推定


> **メモ**: `prompts` 内の各ファイルはユーザーが自由に書き換えてカスタマイズ可能です。


### 概要
- OpenAI / Gemini / ローカルLLM（Ollama等）に対応
- 実験概要自動要約・マテリアルインデックス（MI）自動推定・データ品質評価・実験手法分析など
### AI機能の利用準備
1. `input/ai_config.json` にAPIキー・利用モデル等を記載
2. `input/ai/prompts/` ディレクトリにプロンプトファイルを配置（カスタマイズ可）
3. 必要に応じて `arim_exp.xlsx`（実験情報定義）、`MI.json`（マテリアルインデックス定義）等を用意

#### ai_config.json 設定例
```json
{
  "ai_providers": {
    "openai": { "enabled": true, "api_key": "API_KEY_FOR_OPENAI", ... },
    "gemini": { "enabled": true, "api_key": "API_KEY_FOR_GEMINI", ... },
    "local_llm": { "enabled": true, "base_url": "http://localhost:11434/api/generate", ... }
  },
  "default_provider": "gemini",
  "timeout": 30,
  "max_tokens": 1000,
  "temperature": 0.7
}
```
※詳細なモデルリスト・パラメータはサンプルファイル参照

#### プロンプトカスタマイズ
`input/ai/prompts/` 配下の各テキストファイル（例：quality_assessment.txt, dataset_explanation.txt など）は自由に編集・追加可能です。

#### ローカルLLM利用時の注意
Ollama等のローカルLLMサーバーが必要です。`local_llm`の`base_url`を適切に設定してください。

> **注意**: APIキーは各自取得し、`ai_config.json` に記載してください。

---
