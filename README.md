# DICE/RDE システム操作支援ツール

---

**バージョン: v1.12.6（2025-08-19）**
---

## v1.12.6 変更点（要約）
- ドキュメント・README最新版に更新（配布構成・実行方法・注意事項統一）
- v1.12.5までの修正・クリーンアップ
---
# 配布用ディレクトリ構成

このリポジトリはバイナリ配布専用です。以下のファイル・フォルダが含まれます。

- `arim_rde_tool.exe` : メインアプリケーション
- `docs/README.txt` : 簡易マニュアル
- `docs/login.txt.sample` : ログイン情報サンプル
- `docs/list.txt.sample` : リストサンプル

## ファイルツリー例
```
.
├── arim_rde_tool.exe
├── docs/
│   ├── README.txt
│   ├── login.txt.sample
│   ├── list.txt.sample
├── input/
│   ├── login.txt
│   ├── list.txt
├── output/
│   └── ...
```

## 実行方法
1. 必要に応じて `input/` フォルダを作成し、以下のファイルを配置してください。
  - `login.txt`: 自動ログイン用の情報を記載
  - `list.txt`: 一括取得用のリストを記載
2. `arim_rde_tool.exe` をダブルクリックして実行します。
3. 出力は `output/` フォルダに保存されます。

## 出力例
```
output/
├── datasets/
│   ├── JPMXP12xxTUzzzz/　　　（課題番号）
│   │   ├── .datatree.json　　（不使用）
│   │   ├── データセット/   (データセット名)
│   │   │   ├── aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.json  (書誌情報　JSON　通常版)
│   │   │   ├── filelist.json (不使用)
│   │   │   ├── 差分_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.txt　 (不使用)
│   │   │   ├── サブデータセット/　（サブデータセット名）
│   │   │   │   ├── 01234567-1234-5678-9999-000000000000.json 　 (不使用)
│   │   │   │   ├── file01.png
│   │   │   │   ├── ...
│   │   │   │   ├── filexx.png
│   │   ├── 非開示_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.json　 (書誌情報　JSON　非開示)
│   ├── JPMXP12xxTUyyyy/
├── log/ （デバッグ用）（不使用）
├── info.txt　（デバッグ用）（不使用）
```

## 注意事項
- 必ずこのディレクトリ内のファイルをすべて同じ場所に配置してください。
- 詳細な使用方法は、GitHubリポジトリのREADMEをご参照ください。
- RDEへログインを繰り返すと、正しいパスワードでログインしているにもかかわらずログインが失敗することがあります。その場合は、パスワードを再発行するとアクセスできるようになる場合があります。
# DICE/RDE システム操作支援ツール

---

**バージョン: v1.12.4（2025-08-17）**
---




## v1.12.4 変更点（要約）
- パス依存修正・バイナリ化対応強化
- config.common.pyの定数追加・パス管理統一
- ImportError修正・相対パス問題解決
- バックアップファイル削除・不要ファイル整理
- 配布用ディレクトリ構成・input/outputの扱い明記
- v1.12.3までのクリーンアップ・UI/UX改善・パフォーマンス最適化
---

## 配布用ディレクトリ構成

このリポジトリはバイナリ配布専用です。以下のファイル・フォルダが含まれます。

- `arim_rde_tool.exe` : メインアプリケーション
- `docs/README.txt` : 簡易マニュアル
- `docs/login.txt.sample` : ログイン情報サンプル
- `docs/list.txt.sample` : リストサンプル
- `input/` : ログイン・リストファイル配置用
- `output/` : データ・画像・ログ出力先

### 配布時のinput/outputの扱い
- バイナリ配布時は `input/`・`output/` をバイナリと同じ階層に配置
- 開発時は `src/input`・`src/output` を使用

### 実行方法
1. 必要に応じて `input/` フォルダを作成し、以下のファイルを配置
  - `login.txt` : 自動ログイン用情報
  - `list.txt` : 一括取得用リスト
2. `arim_rde_tool.exe` をダブルクリックで実行
3. 出力は `output/` フォルダに保存

### 出力例
```
output/
├── datasets/
│   ├── JPMXP12xxTUzzzz/（課題番号）
│   │   ├── ...（データセット・画像・JSONファイル）
│   └── ...
├── log/
├── images/
└── ...
```

---

## クラス分離・リファクタリング方針
- UI/ロジック分離：Browserクラス（UI/WebView）、DataManagerクラス（API/データ処理）
- 今後も機能ごとにクラス分離・リファクタリングを進行

---

## 詳細・最新情報
- 詳細な使い方・注意事項は [docs/README.txt](docs/README.txt) を参照
- 最新リリース・リリースノートは [GitHubリリースページ](https://github.com/MNagasako/misc-rde-tool-public/releases) を参照


このリポジトリは、DICE/RDEシステムの利用支援ツールのバイナリ配布専用です。
個人が便利のために作成したもので、自由にご利用いただけますが、**無保証**です。

---

## 主な機能（抜粋）
- データ取得：RDEからデータセットの書誌情報・画像サムネイル取得
- 基本情報取得・XLSX出力
- データ登録・添付ファイル登録（uploadId重複対策済み）
- サブグループ作成・データセット作成・設定・リクエスト解析（開発/テスト中）

---


## ダウンロード

最新版バイナリは以下より取得してください。  
https://github.com/MNagasako/misc-rde-tool-public/releases

---


## 使用方法

### 1. 初回起動時の警告について

Windowsのセキュリティ警告やアンチウイルスによりブロックされる場合があります。  
必要に応じて例外設定してください。

<img width="532" height="498" alt="2025-07-31_18h22_53" src="https://github.com/user-attachments/assets/5117baeb-973c-4a7d-aed6-8f2d58400f26" />
<img width="532" height="498" alt="2025-07-31_18h23_02" src="https://github.com/user-attachments/assets/56e2ecce-466c-420e-ba84-95fc0eceacb5" />


### 1. ログイン
<img width="1062" height="698" alt="2025-07-31_10h49_43" src="https://github.com/user-attachments/assets/c9e7f1c9-cb3f-4f39-9572-693378c33d40" />
RDEアカウントでログインしてください。自動ログインしたい場合は、`input/login.txt` ファイルの先頭に以下の内容を保存してください（DICEアカウントのみ対応）。

```txt
username(mail)
password
dice
```

---

### 2. データ取得（旧方式）
<img width="1062" height="772" alt="2025-07-31_10h55_14" src="https://github.com/user-attachments/assets/a51db1a7-1fce-469b-a912-7d213186b8c8" />
ARIM課題番号を入力し「実行」ボタンをクリックすると、該当課題のデータセットJSONや画像ファイルを取得できます。

- JSONファイルは匿名化版が生成されます。
- WEBVIEW経由のためダウンロードに時間がかかります。
- `input/login.txt` に複数課題番号を記載しておくと「一括実行」ボタンでまとめて処理できます。

```txt
JPMX12xxTUxxxx
JPMX12xxTUyyyy
JPMX12xxTUzzzz
```

---

### 3. 基本情報取得
<img width="1062" height="586" alt="2025-07-31_10h50_46" src="https://github.com/user-attachments/assets/95e8a940-37c6-4f28-b202-84076ed8a382" />
「基本情報」メニューで「基本情報取得（ALL または 検索）」と「invoice_schema取得」を実行してください
####基本情報取得
データセット一覧ページの検索機能で抽出されるデータセットと同じです。
- ALL ログイン中のユーザーがアクセスできる全データセット
- 検索　+　検索窓は空欄　：　検索窓にログイン中のユーザーの名前を入れて検索されるデータセット
- 検索　+ 検索窓にキーワード　：　通常の検索結果



- **（初回は時間がかかります）。
- **ホントにかかります。特にALLは。二回目以降は不足分だけ取得します。コーヒーでも飲んでお待ちください。
- ** 進んでいるかどうか不安な時は'output/rde/data/datasets'　と　'output/rde/data/dataEntry' の中身を確認しましょう。ゆっくり増えていればOK


#### データ取得2（新方式）
<img width="1062" height="528" alt="2025-07-31_11h54_40" src="https://github.com/user-attachments/assets/cb5fd9dc-d093-47a5-9bd0-df88b75d0764" />
1. 基本情報取得後、ドロップダウンリストにアクセス可能な課題（データセット）が表示されます。
2. 「選択データセットのファイルリスト取得」ボタンで、該当データセットの書誌情報JSONと全画像ファイル（構造化済み）を取得できます。
3. 書誌情報は匿名化版が生成されます。

---

#### サブグループ作成
<img width="1062" height="680" alt="2025-07-31_10h50_41" src="https://github.com/user-attachments/assets/8a9eb378-896f-4546-8aff-82c4c6aa8a45" />
サブグループ作成時は以下の手順で操作します。

1. グループメンバー選択欄で管理者（オーナー）・代理管理者（ASSISTANT）を選択
2. グループ名・説明・課題番号（課題番号:課題名, ...）を入力
3. 「サブグループ作成」ボタンで作成
4. 作成後は「基本情報」メニューで共通情報を再取得（リスト反映のため）

※ login/rde-member.txt にメールアドレスと権限を記載しておくと、自動選択されます。
（#行はコメントです）

```txt
# mailaddress , role(1=OWNER,2=ASSISTANT),canCreateDatasets (1=True) , canEditMembers(1=True),;
xxxxxxxxxx@tohoku.ac.jp,2,1,1;
yyyyyyyyyy@tohoku.ac.jp,2,1,1;
zzzzzzzzzz@tohoku.ac.jp,2,1,1;
wwwwwwwwww@tohoku.ac.jp,1,1,1;
```

---

#### データセット開設
<img width="1062" height="528" alt="2025-07-31_10h51_01" src="https://github.com/user-attachments/assets/22f8d8f1-9f92-40e0-bab6-10e6cf0588cf" />
データセット開設時は以下の手順で操作します。

1. サブグループを選択（補完検索可）
2. データセット名・エンバーゴ終了日・テンプレート名を入力
3. 広域シェア・匿名化の有無を選択
4. 「データセット開設実行」ボタンで作成
5. 作成後は「基本情報」メニューで共通情報を再取得

---

#### データ登録
<img width="1062" height="791" alt="2025-07-31_10h54_30" src="https://github.com/user-attachments/assets/afc6fdc7-2342-4f31-a212-892261afd023" />
データ登録時は以下の手順で操作します。

1. データセットを選択（補完検索可）
2. データ名・説明・実験ID・参考URL・タグ・試料情報・固有情報を入力
3. データファイル（必須）・添付ファイル（任意）を選択
4. 「データ登録」ボタンで登録（同一データセットに連続登録可）

---

#### リクエスト解析（開発用）
- REST APIの解析用

#### 設定（未実装）

---

## 注意事項・免責
- 本リポジトリはバイナリ配布専用です。開発・ソース管理は別リポジトリで行っています。
- **本ツールは個人が便利のために作成したもので、無保証です。いかなる損害・不具合についても一切責任を負いません。**
- **再配布・転載は禁止します。必ずこのサイト（GitHub Releases）から最新版をダウンロードしてください。**
- ARIMデータ提供システムへの登録機能はありません（登録は手動でお願いします）。
- ご要望があれば対応するかもしれません。
- ご質問・不具合報告は開発用リポジトリのIssueをご利用ください。

---


---


- v1.12.6（2025-08-19）: ドキュメント・README最新版に更新（配布構成・実行方法・注意事項統一）
- v1.12.5（2025-08-18）: AI機能の包括的強化・レスポンス情報管理・CLI版AIテストツール追加
- v1.12.4（2025-08-17）: パス依存修正・バイナリ化対応強化
- v1.12.3: クリーンアップ・UI/UX改善・パフォーマンス最適化
- v1.12.2: 機能追加・リファクタリング
- v1.12.1: ドキュメント更新・細部修正
- v1.12.0: 内部更新のみ
- v1.11.1: 内部更新のみ
- v1.11.0: ドキュメント更新
- v1.9.11: 内部更新のみ
- v1.9.10: 内部更新のみ
- v1.9.9: 内部更新のみ
- v1.9.8: 内部更新のみ
- v1.9.7: 内部更新のみ
- v1.9.6: 内部更新のみ
- v1.9.5: 内部更新のみ
- v1.9.4: 内部更新のみ
- v1.9.3: uploadId重複バリデーションエラー対策、payload仕様・ドキュメント最新化
- v1.9.2b: summary.xlsx仕様統一、細部修正
- v1.7.2: サニタイズ処理統一・循環インポート修正

リリースページ: https://github.com/MNagasako/misc-rde-tool-public/releases

## ライセンス・問い合わせ
- ライセンス: 未定
- 制作: 東北大金研 長迫



## 関連ツール
- https://github.com/MNagasako/BJB-PathFlattener
