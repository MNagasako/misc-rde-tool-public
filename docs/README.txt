
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

│   └── ...
```

## 実行方法
1. 必要に応じて `input/` フォルダを作成し、以下のファイルを配置してください。
   - `login.txt`: 自動ログイン用の情報を記載
3. 出力は `output/` フォルダに保存されます。

## 出力例
output/
├── datasets/
│   │   ├── .datatree.json　　（不使用）
│   │   ├── データセット/   (データセット名)
│   │   │   ├── filelist.json (不使用)
│   │   │   ├── 差分_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.txt　 (不使用)
│   │   │   ├── サブデータセット/　（サブデータセット名）
│   │   │   │   ├── 01234567-1234-5678-9999-000000000000.json 　 (不使用)
│   │   ├── 非開示_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.json　 (書誌情報　JSON　非開示)
│   ├── JPMXP12xxTUyyyy/
├── log/ （デバッグ用）（不使用）
├── info.txt　（デバッグ用）（不使用）
```

## 注意事項
- 必ずこのディレクトリ内のファイルをすべて同じ場所に配置してください。
- 詳細な使用方法は、GitHubリポジトリのREADMEをご参照ください。
- RDEへログインを繰り返すと、正しいパスワードでログインしているにもかかわらずログインが失敗することがあります。その場合は、パスワードを再発行するとアクセスできるようになる場合があります。
