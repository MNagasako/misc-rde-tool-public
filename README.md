
<img width="403" height="401" alt="2025-08-22_12h57_27" src="https://github.com/user-attachments/assets/c0db1885-48db-4b95-906a-115ade26d152" />

# ARIM RDE Tool v1.17.5

**ARIM RDE Tool** は、文部科学省 ARIM 事業の研究データ共有サイト（RDE）の Web 操作の煩雑さを緩和し、ユーザー体験（UX）を改善する目的で**個人開発**した Windows 用デスクトップアプリです。本家 RDE サイトの画面・通信動作を観察しながら API リクエストを再現しているため、サイト側の仕様変更等により**一部機能が動作しない**場合があります。

本ツールはログイン済みユーザーの **既存の権限範囲** でのみ動作し、それを超える操作は行いません。通常の個人利用において過大なリスクは小さいと考えますが、RDE サイト側に不具合が存在する場合はその限りではありません。

また、取得可能な情報をローカルにキャッシュして検索・補助機能に利用します。**PC やアカウントを他者と共用する場合はご注意ください。**（起動時にキャッシュを破棄するオプションは今後提供予定です）

> 注意：本リポジトリのコードとドキュメントには AI による生成・補助部分が含まれます。誤りが混在する可能性があります。コードは GPLv3 で公開していますが、個人開発のユーティリティであり、読み物としては面白みが少ないかもしれません。

|  バージョン  |    リリース日   | 主な更新内容                    |
| :-----: | :--------: | :------------------------ |
| v1.17.5 | 2025-09-17 | 安定性向上・細かなバグ修正・ドキュメント整理    |
| v1.17.3 | 2025-09-16 | AI 機能拡張・UI 改善・エラーハンドリング強化 |

---

## 目次

* [主な特徴](#主な特徴)
* [動作環境](#動作環境)
* [ダウンロード](#ダウンロード)
* [インストール](#インストール)
* [設定](#設定)
* [クイックスタート / 使い方](#クイックスタート--使い方)

  * [1. データ取得の事前準備](#1-データ取得の事前準備必須)
  * [2. バージョンアップ時の注意](#2-バージョンアップ時の注意)
  * [3. 初回起動時の警告](#3-初回起動時の警告)
  * [4. 基本情報取得](#4-基本情報取得)
  * [5. データ取得（旧方式）](#5-データ取得旧方式)
  * [6. データ取得 2（新方式）](#6-データ取得-2新方式)
  * [7. サブグループ（研究グループ）](#7-サブグループ研究グループ)
  * [8. データセット開設・修正](#8-データセット開設・修正)
  * [9. データ登録](#9-データ登録)
  * [10. AI テスト](#10-ai-テスト)
* [既知の不具合・注意事項](#既知の不具合注意事項)
* [セキュリティ / プライバシー](#セキュリティ--プライバシー)
* [開発中・ToDo](#開発中todo)
* [主な独自機能 / 非対応・未対応機能](#主な独自機能--非対応未対応機能)
* [Contributing](#contributing)
* [サポート・報告方法](#サポート・報告方法)
* [ライセンス](#ライセンス)
* [関連リンク](#関連リンク)
* [開発者向け: バイナリ化と配布](#開発者向け-バイナリ化と配布)

---

## 主な特徴

* サブグループ・データセットの一括管理・編集
* AI による説明文生成・品質評価（OpenAI / Gemini / ローカル LLM 対応）
* RDE 情報の一括取得・XLSX 出力
* 柔軟なフィルタ・検索・補完機能
* 直感的な GUI・多機能タブ構成
* 設定ファイル（JSON / Excel）による柔軟なカスタマイズ

---

## 動作環境

* Windows 10/11 64bit
* Python 3.10 以降（バイナリ配布版は Python 不要）
* 必要フォルダ：`input/`, `output/`（初回起動時に自動生成）

---

## ダウンロード

最新版バイナリは以下より取得できます。
[https://github.com/MNagasako/misc-rde-tool-public/releases](https://github.com/MNagasako/misc-rde-tool-public/releases)

---

## インストール

1. [Releases](https://github.com/MNagasako/misc-rde-tool-public/releases) から最新版 ZIP をダウンロード
2. ZIP を展開し、`arim_rde_tool.exe` を実行
3. `input/` フォルダに設定ファイルやデータを配置
4. GUI 画面から各種操作を実施

> 詳細は `input-sample/` および `docs/` を参照してください。

---

## 設定

<img width="1062" height="1004" alt="2025-09-17_11h16_05" src="https://github.com/user-attachments/assets/0991e17a-62aa-461d-bc64-8983c694b384" />
<img width="1062" height="1004" alt="2025-09-17_11h17_17" src="https://github.com/user-attachments/assets/65baed9c-e52e-4cb6-9999-5ac6ad100267" />

* 必要に応じてプロキシ設定を行ってください。通常のブラウザでインターネットアクセスできていれば本ツールも使用可能です（認証付きプロキシは未対応）。

> **自動ログイン設定について**
>
> * 「暗号化ファイル」または「OS キーチェーン」への保存を推奨（設定メニューで選択可能）。
>
> * `input/login.txt` への平文保存は **非推奨**。やむを得ず利用する場合は以下形式（DICE のみ）：
>
>   ```txt
>   username(mail)
>   password
>   dice
>   ```
>
> * login.txt 利用時は毎回警告が表示されます。できるだけ安全な保存方法へ移行してください。

---

## クイックスタート / 使い方

> 本章以降の手順・画面例は一部古い内容が含まれる場合があります。最新の機能・仕様は上記各章を参照してください。

### 1. データ取得の事前準備（必須）

* **基本情報取得（ALL または 検索）**
* **サンプル情報強制取得**
* **invoice\_schema 取得**

初回は 20–30 分かかる場合があります。短縮したい場合は「基本情報取得（検索）」で課題番号プリフィックス等により絞り込みを推奨。既存データはスキップされます。

### 2. バージョンアップ時の注意

* `INPUT`・`OUTPUT` はそのまま、EXE のみ差し替えで可。
* 保存形式が変わる場合があるため、更新後はあらためて「データ取得の事前準備」を実行してください。

### 3. 初回起動時の警告

Windows のセキュリティ警告やアンチウイルスによりブロックされる場合は、必要に応じて例外設定を行ってください。

<img width="532" height="498" alt="2025-07-31_18h22_53" src="https://github.com/user-attachments/assets/5117baeb-973c-4a7d-aed6-8f2d58400f26" />
<img width="532" height="498" alt="2025-07-31_18h23_02" src="https://github.com/user-attachments/assets/56e2ecce-466c-420e-ba84-95fc0eceacb5" />

### 4. 基本情報取得

<img width="1062" height="925" alt="2025-08-22_13h50_22" src="https://github.com/user-attachments/assets/bb481a4b-3585-409e-bad3-1941694ee20d" />

* RDE サーバー上のデータをローカルに一括取得し、検索機能を有効化します。
* 初回は時間を要しますが、既存ファイルはスキップされます。
* 強制再取得が必要な場合は対象ファイルを削除して再実行してください。

### 5. データ取得（旧方式）

* 内蔵 **WebView** を用いて RDE の画面にアクセスし、**BLOB 画像を保存**する実装です。**パフォーマンス上の制約**があり、環境によっては取得に時間がかかります。
* **課題番号を指定**すると、関連するデータセットと、それに紐付いた **データエントリー（タイル）** の情報を取得します。
* 可能であれば、後述の **新方式（API 直接ダウンロード）** の利用を推奨します。

### 6. データ取得 2（新方式）

<img width="1062" height="632" alt="2025-09-17_11h08_48" src="https://github.com/user-attachments/assets/4d1ff881-9c61-4673-acd3-a22f1ca4b1b3" />
<img width="1062" height="632" alt="2025-09-17_11h08_58" src="https://github.com/user-attachments/assets/6865cdfe-dd10-400e-8c0d-30597bb85712" />

* **API アクセスで直接ダウンロード**する方式です。旧方式に比べて安定性と速度の面で有利です。
* 「データ取得」タブで対象データセットを選択（補完検索可）。
* **選択データセットのファイルを一括取得** で書誌情報・画像をまとめて取得。
* 広域シェア、ユーザーロール、課題番号でリストを絞り込み可能。
* 「ファイルフィルタ」タブで属性・拡張子・サイズ・名称・上限数を設定してから実行。

### 7. サブグループ（研究グループ）

<img width="1062" height="1004" alt="2025-09-17_11h26_44" src="https://github.com/user-attachments/assets/1c1a5902-7bae-43ab-8c75-36ad7a6d8c6c" />
<img width="1062" height="1004" alt="2025-09-17_11h26_54" src="https://github.com/user-attachments/assets/9ddfe44b-0726-439a-9f3a-7b13d5783dc4" />

**新規作成**

1. 役割（Role）を設定（`input/rde-member.txt` でデフォルト指定可）。
2. グループ名・説明・課題番号・研究資金番号を入力。
3. **作成** をクリック。※ **一括作成** は現在利用不可（クラッシュします）。

**修正**

1. サブグループを選択（補完検索・表示フィルタ可）。
2. **サブグループ更新** をクリック。

   * **RDE サブグループページを開く**：RDE 上の同ページを開きます（事前ログイン要）。
   * **関連試料抽出**：所属試料一覧を表示し、クリックでサンプルページを開きます。

### 8. データセット開設・修正

<img width="1062" height="528" alt="2025-07-31_10h51_01" src="https://github.com/user-attachments/assets/22f8d8f1-9f92-40e0-bab6-10e6cf0588cf" />
<img width="1062" height="710" alt="2025-08-22_14h15_23" src="https://github.com/user-attachments/assets/349caf93-a1d5-4c84-9a85-ee3c1e955f27" />

* サブグループを選択（補完検索対応）
* 課題番号を選択（登録済みである必要あり）
* データセット名・テンプレートを指定
* 広域シェア・匿名化オプションを選択
* **データセット開設実行** をクリック

### 9. データ登録

<img width="1062" height="532" alt="2025-08-22_14h26_17" src="https://github.com/user-attachments/assets/9904b0d9-436e-4801-bf78-a0c2c42dbf15" />

* データセットを選択
* データ名・説明・試料情報を入力
* ファイルを添付
* **データ登録** をクリック

### 10. AI テスト

<img width="1062" height="832" alt="2025-08-22_14h31_56" src="https://github.com/user-attachments/assets/c5dae4c6-b4cb-4341-93bd-45f0381d57bd" />
<img width="1062" height="832" alt="2025-08-22_14h33_31" src="https://github.com/user-attachments/assets/1f58b255-b30d-4623-8f75-d7503e391e32" />

* `input/ai_config.json` と `input/ai/` を準備
* AI プロバイダ・モデルを選択
* 課題番号・実験データを選択
* 利用報告書データの使用有無を選択
* 分析方法を選び **AI 分析実行**

> **AI 設定ファイルについて**
> 設定は `input/ai_config.json` に記載します。以下は概要です。
>
> ```json
> {
>   "ai_providers": {
>     "openai": { "enabled": true, "api_key": "API_KEY_FOR_OPENAI", "base_url": "https://api.openai.com/v1", "models": ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o4-mini-deep-research", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"], "default_model": "gpt-4o-mini" },
>     "gemini": { "enabled": true, "api_key": "API_KEY_FOR_GEMINI", "base_url": "https://generativelanguage.googleapis.com/v1beta", "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"], "default_model": "gemini-2.0-flash" },
>     "local_llm": { "enabled": true, "base_url": "http://localhost:11434/api/generate", "models": ["gemma3:1b", "gemma3:4b", "gemma3:12b", "gemma3:27b", "llama3.1:8b", "deepseek-r1:7b", "deepseek-r1:8b", "deepseek-r1:14b", "deepseek-coder-v2:16b", "qwen2.5:7b-instruct", "qwen2.5:14b-instruct", "qwen2.5-coder:7b-instruct", "gpt-oss:20b"], "default_model": "gemma3:12b", "note": "Ollama 等のローカル LLM サーバーが必要です。" }
>   },
>   "default_provider": "gemini",
>   "timeout": 30,
>   "max_tokens": 1000,
>   "temperature": 0.7
> }
> ```
>
> * OpenAI / Gemini / ローカル LLM の 3 系統に対応。
> * `local_llm` 利用時は **Ollama などのローカルサーバー** が必要です。

---

## 既知の不具合・注意事項

> ⚠️ ディスプレイサイズや解像度により、ウインドウや文字サイズが意図せず変化する場合があります。開発環境（特定の解像度・DPI）でのみ検証しています。他環境では UI 要素の重なり・極小表示等が起きる可能性があります。発生時は **OS / 解像度 / DPI** を添えて作者までご連絡ください。

> **RDE リンク機能** を使用する場合は、事前にブラウザ（Chrome 推奨）で RDE へログインしておいてください（Windows/Chrome のみ確認済み）。

---

## セキュリティ / プライバシー

* **権限制御**: 本ツールは RDE アカウントで付与されている権限の範囲でのみ API / Web 操作を行います。それを超える操作はできません。
* **ローカルキャッシュ**: 取得した情報の一部をローカルに保存して検索や補助機能に利用します。PC やユーザーアカウントを他者と共用する場合は、キャッシュの扱いにご注意ください。（将来的に「起動時にキャッシュを破棄」オプションを提供予定）
* **ネットワーク**: プロキシ経由での通信に対応（認証付きプロキシは未対応）。社内ネットワークポリシーに従ってご利用ください。
* **リスク認識**: 本ツールは RDE サイトの仕様に依存しており、サイト側の変更や不具合により想定外の動作をする可能性があります。重要な操作の前には内容を確認し、必要に応じてブラウザ上で最終確認してください。

---

## 開発中・ToDo

* AI 機能の継続的拡張（プロバイダ追加・プロンプトカスタマイズ性向上）
* Data Fetch 2 のフィルタ UI / ロジック最終調整
* PyQt のライセンス上の理由から将来的に **PySide** への移行を検討

---

## 主な独自機能 / 非対応・未対応機能

*用語*: **非対応**＝意図的に対応しない、**未対応**＝まだ実装していない。

### 主な独自機能

* サブグループ：Role によるフィルタ表示、試料情報抽出、RDE 連携
* データセット：タクソノミーキービルダー、TAG ビルダー、関連データセットの簡易検索・設定
* データ登録：データセットの簡易指定、補完フィルタ
* RDE 情報取得（基本情報）：一括取得、XLSX 出力
* AI テスト機能

### 主な非対応機能（意図的に対応しない）

* 削除系 API リクエスト（安全性のため未実装。編集ページへのリンクから RDE 上で削除）

### 主な未対応機能（今後対応予定）

* データカタログの作成・編集
* 送り状編集（対応予定）
* 添付ファイル削除
* CSV によるグループメンバー一括置換
* 関連試料設定（対応予定）

---

## Contributing

個人開発のため、**Pull Request は受け付けていません**。バグや誤記のご連絡は、作者へ **直接** お知らせください（メール等、把握している連絡手段で構いません）。

ご連絡の際に含めていただけると助かる情報：

* 事象の概要 / 期待される動作 / 実際の結果
* 再現手順（できれば最小手順）
* 画面キャプチャやログ
* 環境情報（OS / 解像度 / DPI / アプリのバージョン）

---

## サポート・報告方法

サポートや不具合報告は、**作者へ直接ご連絡**ください。迅速な対応を保証するものではありませんが、可能な範囲で対応します。ドキュメントやコードには AI による生成・補助部分があり、誤りが含まれる可能性があります。

---

## ライセンス

本ツールは GPLv3 で公開しています。詳細は `LICENSE` をご覧ください。

---

## 関連リンク

* [最新版バイナリ・リリースノート](https://github.com/MNagasako/misc-rde-tool-public/releases)
* [CHANGELOG（詳細な更新履歴）](docs/CHANGELOG.md)
* [AI 機能ガイド](docs/AI_FEATURE_GUIDE.md)
* [バイナリビルド手順](docs/binary_build_notes.md)

---

## 開発者向け: バイナリ化と配布

### バイナリ化方法（開発用リポジトリでの手順）

1. **仮想環境の有効化と依存モジュールのインストール**

   ```powershell
   # PowerShell 例
   cd C:\\vscode\\rde
   .\\.venv\\Scripts\\Activate.ps1
   pip install -r requirements.txt
   ```
2. **PyInstaller によるバイナリ化**

   ```powershell
   pyinstaller --exclude-module pytest --noconsole --onefile --icon "src/image/icon/icon1.ico" --add-data "src/image;image" --add-data "config;config" --add-data "src/js_templates;js_templates" src/arim_rde_tool.py
   ```

* 生成物：`dist/arim_rde_tool.exe`

### 配布関連

* `dist/arim_rde_tool.exe` — メイン実行ファイル
* `dist/arim_rde_tool_v*.zip` — 配布用圧縮ファイル
* `input-sample/` — サンプル入力ファイル群

### ドキュメント

* `README.md` — メイン説明・ダウンロードリンク
* `docs/binary_build_notes.md` — バイナリ配布・使用方法
* `docs/CHANGELOG.md` — 変更履歴
* `docs/RELEASE_NOTES_v*.md` — リリースノート
* `VERSION.txt` — バージョン情報

### 設定・管理

* `.gitignore` — バイナリファイル除外設定
* `rde-public.code-workspace` — VS Code ワークスペース設定
