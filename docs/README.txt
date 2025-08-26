# 配布用ディレクトリ

このディレクトリには、バイナリ配布に必要なファイルが含まれています。

**バージョン: 1.7.0**

## 同梱ファイル
- `arim_rde_tool.exe`: メインアプリケーション（バイナリ名を現状に合わせ修正）
- `docs/README.txt`: 簡易マニュアル
- `docs/login.txt.sample`: ログイン情報サンプル
- `docs/list.txt.sample`: リストサンプル

## ファイルツリー
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
│   │   │   ├── 非開示_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.json　 (書誌情報　JSON　非開示)
│   ├── JPMXP12xxTUyyyy/
├── log/ （デバッグ用）（不使用）
├── info.txt　（デバッグ用）（不使用）
```

## 注意事項
- 必ずこのディレクトリ内のファイルをすべて同じ場所に配置してください。
- 詳細な使用方法は、GitHubリポジトリのREADMEをご参照ください。
- RDEへログインを繰り返すと、正しいパスワードでログインしているにもかかわらずログインが失敗することがあります。その場合は、パスワードを再発行するとアクセスできるようになる場合があります。

## 問い合わせ
- 作成者: 東北大学 長迫
- GitHubリポジトリ: https://github.com/MNagasako/misc-rde-tool-public

クラス分離・リファクタリング方針（2025年7月時点）

- UI/ロジック分離：
  - Browserクラス（arim_rde_tool.py）はUI・WebView制御・ユーザー操作のみ担当。
  - DataManagerクラス（src/classes/data_manager.py）はAPIアクセス・データ抽出・保存・ID抽出等のデータ処理を担当。
- 進行中のリファクタリング：
  - データ取得・解析系メソッド（例: extract_ids_and_names等）は順次DataManagerへ移管。
  - UIからはDataManager経由でデータ操作を呼び出す設計へ移行中。
- 今後の予定：
  - 認証・ファイル管理・blob画像抽出・匿名化等も機能別クラスへ分離予定。
  - ドキュメントも現状に合わせて随時更新。

# バイナリ配布時のinput/outputの扱いについて
- バイナリ配布時は、`input/`・`output/` フォルダをバイナリと同じ階層に配置してください。
- 開発時は `src/input`・`src/output` を使用します。
- これは現状の動作であり、正しく動作しています。
