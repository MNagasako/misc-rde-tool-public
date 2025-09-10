# データ登録機能 詳細ドキュメント

## 概要
RDEシステムへのデータ登録（ファイルアップロード、メタデータ入力、進捗管理等）をGUIで提供する機能群。

- 構成:
  - core/: ロジック（登録処理、API連携）
  - ui/: UI部品（タブ・ウィジェット）
  - util/: フィルタ・補助関数

## 実装・主要クラス/関数

### core/data_register_logic.py
- run_data_register_logic: データ登録のメイン処理。ファイル選択、トークン・データセット情報検証、プレビュー生成、登録処理呼び出し。
  - 入力: parent, bearer_token, dataset_info, form_values, file_paths, attachment_paths
  - 出力: UI通知、登録処理の実行
  - 依存: api_request_helper, config.common
- _continue_data_register_process: 実際の登録処理（詳細は後続行で要確認）

### core/data_register_widget.py
- DataRegisterWidget: データ登録用のUIウィジェット
  - UI初期化、データセット選択、ファイル選択、添付ファイル管理など
  - 入力: parent, bearer_token
  - 出力: UI表示、ユーザー操作イベント
  - 依存: PyQt5, config.common

### ui/data_entry_tab_widget.py
- DataEntryTabWidget: データ登録機能のタブUI
  - レイアウト最適化、ファイルアップロード・メタデータ・進捗タブ生成
  - 入力: parent
  - 出力: UI表示
  - 依存: PyQt5

### util/data_entry_filter_checkbox.py
- チェックボックス付きフィルタUI
- get_colored_dataset_display_name: データセット名の装飾表示
- 依存: data_entry_filter_util, PyQt5

### util/data_entry_filter_util.py
- データ登録用フィルタ補助関数群
  - get_current_user_id_for_data_entry
  - get_datasets_for_data_entry
  - get_subgroups_for_data_entry
  - get_user_role_in_dataset
- 入力: 設定ファイルパス
- 出力: ユーザーID、データセットリスト等
- 依存: config.common

## 関数一覧・入出力・依存関係マップ

| 関数名 | 入力 | 出力 | 依存 |
|--------|------|------|------|
| run_data_register_logic | parent, bearer_token, dataset_info, ... | UI通知・登録処理 | api_request_helper, config.common |
| _continue_data_register_process | ... | 登録処理 | 上記同様 |
| DataRegisterWidget | parent, bearer_token | UI表示 | PyQt5, config.common |
| DataEntryTabWidget | parent | UI表示 | PyQt5 |
| get_colored_dataset_display_name | dataset(dict) | str | data_entry_filter_util |
| get_current_user_id_for_data_entry | なし | str | config.common |
| get_datasets_for_data_entry | なし | list | config.common |
| get_subgroups_for_data_entry | なし | list | config.common |
| get_user_role_in_dataset | dataset, user_id | str | config.common |

## 不要関数の洗い出し（暫定）
- 取得した範囲では「未使用」や「重複」関数は見当たりませんが、全体の依存関係解析・grepで未使用関数を追加調査します。

---

# データ登録機能 改善計画

1. 依存関係の明確化
   - api_request_helper・config.commonの利用箇所を整理
   - UIとロジックの責務分離を徹底
2. 不要コード・未使用関数の削除
   - ワークスペース全体で未使用関数をgrepし、削除候補リストを作成
3. テスト・例外処理強化
   - ファイル選択・API通信・UI操作の例外処理を網羅
   - ユニットテストの追加
4. ドキュメント・コメント充実
   - 各関数のdocstring・型アノテーション追加
   - 利用例・画面遷移図の作成

---

（このドキュメントは自動生成のドラフトです。今後、詳細な関数定義・利用箇所・未使用関数リスト・改善案を随時追記してください）
