# DICE/RDE システム操作支援ツール

---

**バージョン: v1.13.1（2025-08-22）**

---

## v1.13.1 変更点（要約）
- 安定版リリース

---

## 実行方法

0. アプリを起動すると、`input/` および `output/` フォルダが自動生成されます。
1. 必要に応じて `input/` フォルダを作成し、以下のファイルを配置します：
   - `login.txt`: 自動ログイン用の情報を記載
   - `list.txt`: 一括取得用の課題番号リストを記載
2. `arim_rde_tool.exe` をダブルクリックで起動
3. 出力は `output/` フォルダに保存されます

> **注意**: このリポジトリはバイナリ配布専用です。開発用ソースは別リポジトリで管理されています。

---

# 主な機能（RDE補助ツール v1.13.1）

## データ取得・登録機能
- **書誌情報取得**：課題番号リストからRDEの書誌情報とサムネイル画像を自動取得（JSON形式）
- **データ取得2（ファイル一括取得）**：データセットに紐づくファイルを一括ダウンロード
- **データセット新規開設**：サブグループや課題番号を指定してデータセットを作成、エンバーゴ設定対応
- **データ登録**：実験情報・試料情報・添付ファイルを登録、IDやファイルパスを自動生成

---

## サブグループ管理機能
- **サブグループ新規作成**：メンバーと権限（OWNER/ASSISTANT）を指定、一括登録も可能
- **サブグループ修正**：既存グループの構成・課題番号・権限を変更可能

---

## 出力・可視化機能
- **XLSX出力**：ユーザー・サブグループ・データセット一覧をExcel出力（フィルタ対応）
- **リクエスト解析**：RDE APIリクエストを可視化、DevTools不要でデバッグ可能

---

## AI連携機能（試験実装）
- **AIテスト機能**
  - OpenAI / Gemini / ローカルLLM対応
  - 実験概要自動要約・マテリアルインデックス推定

---

## 補足
- 設定タブは v1.13.1 時点で未実装
- RDEアカウント情報があれば基本機能は利用可能
- API仕様変更時はバージョン更新が必要

---

## ダウンロード
最新版バイナリは以下より取得できます：
https://github.com/MNagasako/misc-rde-tool-public/releases

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

### 6. データセット開設
<img width="1062" height="528" alt="2025-07-31_10h51_01" src="https://github.com/user-attachments/assets/22f8d8f1-9f92-40e0-bab6-10e6cf0588cf" />

- サブグループと課題番号を選択
- データセット名やテンプレートを指定
- 作成後は基本情報を更新

---

### 7. データ登録
<img width="1062" height="791" alt="2025-07-31_10h54_30" src="https://github.com/user-attachments/assets/afc6fdc7-2342-4f31-a212-892261afd023" />

- データセットを選択し、必要情報を入力
- データファイルを添付して「データ登録」ボタンで実行

---

### 8. その他
- **リクエスト解析**：REST APIデバッグ用
- **設定タブ**：未実装

---

## 注意事項・免責
- このリポジトリはバイナリ配布専用
- 本ツールは**個人開発のため無保証**
- 再配布・転載は禁止
- ARIMデータ提供システムへの登録機能はありません

リリースページ：https://github.com/MNagasako/misc-rde-tool-public/releases

## ライセンス・問い合わせ
- ライセンス: 未定
- 制作: 東北大金研 長迫

## 関連ツール
- https://github.com/MNagasako/BJB-PathFlattener
