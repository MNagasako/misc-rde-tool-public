このファイルは旧版の簡易マニュアルです。最新版の情報はREADME.mdをご参照ください。
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

## v1.14.1 主な改善点（2025-08-28）
## v1.18.0 主な改良点（2025-10-02）
- 新機能・改善点の記載（例：UI改善、バグ修正、パフォーマンス向上など）
- 軽微な修正・安定性向上

## 問い合わせ
- UI/ロジック分離：
  - Browserクラス（arim_rde_tool.py）はUI・WebView制御・ユーザー操作のみ担当。
  - DataManagerクラス（src/classes/data_manager.py）はAPIアクセス・データ抽出・保存・ID抽出等のデータ処理を担当。
- 完了済みリファクタリング：
  - データ取得・解析系メソッド（例: extract_ids_and_names等）は順次DataManagerへ移管完了。
  - UIからはDataManager経由でデータ操作を呼び出す設計へ移行完了。
- 企業環境対応：
  - プロキシ対応・SSL証明書管理・CA証明書機能の完全対応。
  - PyInstallerバイナリ配布での安定動作確認済み。

# バイナリ配布時のinput/outputの扱いについて
- バイナリ配布時は、`input/`・`output/` フォルダをバイナリと同じ階層に配置してください。
- 開発時は `src/input`・`src/output` を使用します。
- これは現状の動作であり、正しく動作しています。
