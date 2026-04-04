# 更新履歴

このタブは、About タブの「更新点（リリースノート）」部分を分離したものです。

## 最新版の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.46）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| Basic Infoバックグラウンド取得 | `background_fetch_manager.py` を導入し、個別データ取得をバックグラウンド実行しながらタブ操作を継続可能に改善。 |
| Basic Info進捗表示 | `basic_unified_status_widget.py` に個別データ取得のプログレスバー・段階ラベル・中止ボタンを追加。 |
| dataset一覧再取得 | `dataset.json` 一覧は常に再取得し、差分判定の基準を最新化。個別 dataEntry / invoice は内部フィルタで必要分のみ取得。 |
| 失敗記録 | invoice 取得の失敗理由を `_summary.json` に保持し、既知の失敗エントリ再試行を抑制。 |
| テスト/品質 | 背景取得マネージャー、dataEntry / invoice の事前フィルタ、件数進捗表示のユニットテストを追加。 |

## v2.5.46 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.46）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| Basic Infoバックグラウンド取得 | `background_fetch_manager.py` を追加し、サンプル / データセット個別 / dataEntry / invoice / invoiceSchema の取得をバックグラウンドスレッドで段階実行可能に整理。 |
| Basic Info進捗UI | `basic_unified_status_widget.py` で個別データ取得用の進捗バー、段階別メッセージ、中止ボタン、埋め込み worker 管理を追加。 |
| Basic Info取得戦略 | `basic_info_logic.py` で `dataset.json` は常時再取得へ統一し、dataEntry / invoice は事前フィルタで新規・欠損・未成功分のみ取得するよう改善。 |
| invoice失敗記録 | invoice 取得失敗を `_summary.json` の `failed` に保存し、既知のアクセス拒否や失敗済み entry の無駄な再試行を回避。 |
| 起動導線 | `ui_basic_info.py` で Phase 1 の共通情報取得後に Phase 2 のバックグラウンド取得を開始する導線へ整理し、検索モードでも同じ説明文と進捗制御を反映。 |
| テスト/品質 | `test_background_fetch_manager.py`、`test_data_entry_fetch_prefilter.py`、`test_invoice_progress_and_bg_guard.py`、`test_invoice_schema_prefilter.py`、`test_basic_info_force_download_false_fetches_lists.py` を追加・更新。 |

## v2.5.44 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.44）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| 外部アクセスモニター | `external_access_monitor.py` / `external_access_monitor_widget.py` を追加し、HTTPリクエストの送信先・頻度を UI で可視化。`http_helpers.py` にモニター通知フックを実装。 |
| サブグループ完全性チェック | `basic_info_logic.py` で subGroupsAncestors の完全性確認と重複メッセージ抑制を追加。 |
| マスタデータ強化 | `master_data.py` / `master_data_tab.py` にマテリアルインデックス・タグマスタの進捗コールバックと CSV/XLSX エクスポート・自然ソートを実装。 |
| data_fetch2 | `data_fetch2_widget.py` / `data_fetch2_tab_widget.py` で QComboBox パフォーマンス最適化とウィジェット初期化改善。`bulk_dp_tab.py` に dataset.json キャッシュを追加。 |
| AIプロバイダー到達性 | `ai_manager.py` にプロバイダー到達性チェック機能を追加し、`ai_suggestion_dialog.py`・`dataset_edit_widget.py`・`dataset_open_widget.py` で使用。 |
| TTLキャッシュ | `ttl_cache.py` を追加し、bulk_dp・dataset_open・registration_status 等のキャッシュに適用。 |
| サブグループ編集 | `subgroup_edit_widget.py` でペイロード適用・ユーザーキャッシュクリア・メンバー管理を改善。`remote_resource_pruner.py` を追加。 |
| テスト/品質 | `test_external_access_monitor.py`、`test_external_access_monitor_widget.py`、`test_ttl_cache.py`、`test_ai_manager_reachability.py`、`test_subgroups_ancestors_check.py` 等を追加。 |

## v2.5.43 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.43）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| 終了時スレッド制御 | `thread_registry.py` を導入し、終了時に実行中 QThread の待機または強制停止を選べるよう改善。 |
| AI提案ダイアログ | 保存済みの小さい高さがあっても、初回表示時は画面の利用可能領域基準の高さを優先するよう安定化。 |
| 新規開設2 | 既存データセット読込 UI を遅延構築に変更し、構築中プログレス表示と worker 停止経路を追加。 |
| データセットフィルタ | `show_all()` で大量候補でも即時表示できるよう同期パスを追加し、カーソルキー/ホイール移動時の誤フィルタを防止。 |
| テスト/品質 | スレッド停止制御、AI提案ダイアログ初回高さ、create2 遅延構築、フィルタコンボ操作性の回帰テストを追加。 |

## v2.5.45 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.45）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| 終了時スレッド制御 | `thread_registry.py` を追加し、`arim_rde_tool.py` の closeEvent で実行中スレッド数を確認しつつ、待機または強制停止を選択できるよう更新。 |
| AI提案ダイアログ | `ai_suggestion_dialog.py` で AI拡張各タブの初回高さを保存値ではなく画面の利用可能領域基準で決定し、狭い高さの復元を防止。 |
| 新規開設2 | `dataset_open_widget.py` で create2 タブを初回選択時に構築し、構築中プログレス表示・既存データセット読込 worker の停止経路・対象範囲フィルタを整理。 |
| データセットフィルタ | `dataset_filter_fetcher.py` で `show_all()` 実行時の同期全件表示と、カーソルキー/ホイール操作中にテキスト検索を発火させない制御を追加。 |
| テスト/品質 | `test_close_event_thread_control.py`、`test_ai_suggestion_dialog_initial_height.py`、`test_create2_deferred_build.py`、`test_dataset_filter_fetcher_show_all_sync.py`、`test_dataset_filter_fetcher_index_navigation.py` などを追加・更新。 |
| データ取得2 | `data_fetch2_tab_widget.py` でデータセット取得タブを lazy build 化し、フィルタタブの prewarm を遅延化。初回表示では planned summary の自動集計を行わず、明示選択時だけ更新。 |
| 一括取得（DP） | `bulk_dp_tab.py` でフィルタ候補の bootstrap を非同期化し、起動直後でも検索 UI を先に操作できるよう改善。 |
| 一括取得（DP） | 検索中に進捗詳細ラベルを追加し、進捗件数・抽出見込み件数・速度・ETA を表示。ローカル `output.json` がある場合はそれを優先して高速に一覧化。 |
| UI品質 | `ui_controller.py` で data_fetch2 初回表示時の後段 resize / overlay hide を抑制し、`dataset_open` 再生成時の refresh notifier callback を常に 1 件へ維持。 |
| テスト/品質 | `test_bulk_dp_tab.py`、`test_data_fetch2_bulk_tabs_lazy.py`、`test_data_fetch2_filter_tab_deferred_build.py`、`test_dataset_open_widget_reset.py`、`test_planned_summary_label.py` などを追加・更新。 |

## v2.5.42 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.42）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データポータル | `dataset_upload_tab.py` で書誌情報JSON / コンテンツZIP / データカタログ修正 / ブラウザ表示 / ステータス変更の主要操作を 1 行のアクションボタン列へ整理。 |
| データポータル | 主要操作ボタンに success / info / warning のテーマ別スタイルを割り当て、padding・border・hover / pressed / disabled 表現を統一。 |
| 共有UI | `data_fetch2_widget.py` を共有するドロップダウンのコンボ表示スタイルを維持し、データポータル側へ統合した際のフォントサイズ・最小高さ・背景色の視認性を安定化。 |
| テスト/品質 | `test_dataset_upload_tab.py`、`test_dataset_upload_tab_scroll_and_theme.py`、`test_data_fetch2_combo_font_display.py` を更新し、アクション行レイアウト・ボタンスタイル・共有コンボ表示を回帰検証。 |

## v2.5.41 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.41）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| AI拡張設定 | `ai_extension_config_dialog.py` に prompt assembly 方式選択、source別 override、辞書管理タブを追加し、ボタン定義と辞書育成を同一ダイアログで完結可能に整理。 |
| AI提案/AI CHECK | `AIExtensionConfigManager` と `ai_suggestion_dialog.py` / `quick_ai_suggestion.py` を更新し、データセット説明 AI提案・Quick AI・AI CHECK のテンプレートを個別選択できるよう改善。 |
| Prompt Assembly | `prompt_assembly_runtime_dialog.py` で実行前の runtime override を追加し、`prompt_assembly.py` / `prompt_dictionary_presets.py` で辞書 preset seed、summary cache、output 走査候補生成・評価を実装。 |
| AI設定 | `ai_settings_widget.py` に filtered_embed 辞書サマリと管理ダイアログ導線を追加し、辞書状態の確認を容易化。 |
| データセット選択 | `dataset_filter_fetcher.py` を利用する AI提案系のコンボで、入力中の絞り込み・popup focus・選択維持の安定性を改善。 |
| テスト/品質 | `test_prompt_assembly.py`、`test_prompt_dictionary_presets.py`、`test_ai_extension_config_dataset_desc_prompt_selection.py`、`test_prompt_assembly_runtime_dialog.py`、`test_ai_settings_prompt_dictionary_summary.py`、`test_ai_test2_dialog_dataset_combo_filters.py` などを追加・更新。 |

## v2.5.40 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.40）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| AI設定 | `ai_settings_widget.py` に生成パラメータテーブルを追加し、各パラメータをカスタム送信するかどうかを UI で切り替えられるよう改善。 |
| AI設定 | 問い合わせ最大試行回数を追加し、`ai_manager.py` で OpenAI / ローカルLLM の共通リトライ回数を 1〜5 回で制御。 |
| ローカルLLM | `local_llm.py` で Ollama / LM Studio の既定 endpoint を分離し、host 解決・OpenAI互換URL生成・provider 表示名を整理。 |
| AIテスト | `ui_ai_test.py` で初期化中 progress 表示とローカルランタイム名の反映を追加し、AI設定反映までの状態を可視化。 |
| テスト/品質 | `test_ai_manager_request_retry_openai_local.py`、`test_local_llm_endpoint_parts.py`、`test_local_llm_lm_studio_support.py`、`test_ai_settings_provider_collapse.py`、`test_ai_test_widget_initial_loading.py` を追加・更新し、再試行・URL解決・UI状態を回帰検証。 |

## v2.5.39 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.39）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| 試料一覧2 | `sample_dedup_listing_widget.py` に `_reload_rows()` を追加し、cache_enabled=False の更新ボタン・再リンク後復帰・再読込がキャッシュ経路を通らないよう整理。 |
| 試料一覧2 | `sample_dedup_table_records.py` で dataset detail JSON から group 関連付けと `subjects.grantNumber` を補完し、dataset.json の情報欠落時でも一覧2の join key を復元。 |
| 試料一覧2 | `grant_numbers` は subgroup 側の複数候補より dataset 側の実課題番号を優先する単一値として扱い、一覧2の関連付けを安定化。 |
| テスト/品質 | `test_sample_dedup_table_records.py`、`test_sample_dedup_numeric_range_filter.py`、`test_sample_dedup_widget_creation.py` を更新し、detail fallback と cache 無効時の reload 経路を回帰検証。 |

## v2.5.38 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.38）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| 試料一覧2 | `sample_dedup_listing_widget.py` でタイル数フィルタの初期最小値を 1 に変更し、利用者が 0 / なし へ戻せる操作性は維持。 |
| 試料一覧2 | `sample_dedup_table_records.py` で 一覧2 用のプレースホルダ行生成を追加し、タイル-データセット-課題番号列に 読み込み中 を表示。 |
| 試料一覧2 | 同列で参照エントリーが存在しない場合は エントリー無し を返し、`ThemeKey.TEXT_MUTED` を使った低彩度表示に変更。 |
| テスト/品質 | `test_sample_dedup_table_records.py`、`test_sample_dedup_numeric_range_filter.py`、`test_sample_dedup_widget_creation.py` を更新し、loading/empty/filter 初期値を回帰検証。 |

## v2.5.37 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.37）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| メインウィンドウ | `ui_controller_core.py` と `window_sizing.py` で初回表示時に画面高へフィットしたメインウィンドウのクライアント幅を保持し、子ダイアログが初回幅の基準として参照できるよう修正。 |
| AI説明文提案 | `ai_suggestion_dialog.py` でフレーム込みの中央配置計算を修正し、初回 `resize()` 直後でもダイアログ中心がディスプレイ中心に一致するよう改善。 |
| AI説明文提案 | AI拡張モードの未保存タブで、上下左右50pxマージンを保った画面基準サイズを採用しつつ、タブ別の size/position 記憶を維持。 |
| ファイル抽出設定 | 初回幅をメインウィンドウ初期幅へ揃え、初回高さをディスプレイ高さ基準にしたまま、その後のユーザーリサイズを妨げないよう整理。 |
| テスト/品質 | `test_ai_suggestion_dialog_geometry_persistence.py`、`test_ai_suggestion_dialog_top_align.py`、`test_window_sizing.py`、`test_window_position.py` を更新し、抽出設定タブ初回幅/高さ・中央配置・タブ別 geometry 記憶を回帰検証。 |

## v2.5.36 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.36）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データ登録（一括登録） | `batch_register_widget.py` で固有情報フォーム本体とプレースホルダーの可視状態をトグルへ同期し、summary 状態からデータセットを選んだ場合でも「入力」押下でフォーム本体が展開されるよう修正。 |
| データ登録（一括登録） | フォーム生成時/クリア時/空フォーム生成時に同一の可視性同期処理を通すよう整理し、固有情報項目の有無に応じた表示を安定化。 |
| テスト/品質 | `test_batch_register_toggle_sections.py` に固有情報トグル回帰テストを追加し、関連既存テストとあわせて再検証。 |
| テスト/ビルド | pytest段階ゲート、`run_pre_build_tests.ps1`、`arim_rde_tool_onedir_withtest.spec` を v2.5.36 のリリース導線として同期。 |

## v2.5.35 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.35）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データ登録（一括登録） | `batch_register_widget.py` のファイルセット内容ダイアログで、適用中に別の完了メッセージを同期表示していた経路を廃止。 |
| データ登録（一括登録） | マッピングファイル更新の個別完了ダイアログを抑止できるようにし、内容ダイアログ close 後に 1 回だけ完了通知を出すよう修正。 |
| テスト/品質 | `test_batch_register_fileset_content_dialog.py` を追加し、同期ダイアログ抑止と close 後通知を回帰検証。 |
| テスト/ビルド | `run_pre_build_tests.ps1` の安定化構成と、`arim_rde_tool_onedir_withtest.spec` の VERSION.txt ベース VersionInfo 埋め込みをリリース内容へ反映。 |

## v2.5.34 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.34）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データ登録 | `data_register_tab_widget.py` の登録状況タブ用スクロールラッパーで余剰高さを内容側へ配分するよう調整。 |
| データ登録 | `registration_status_widget.py` のテーブルを `QSizePolicy.Expanding` と layout stretch で構成し、縦方向の余白がテーブル領域へ割り当たるよう修正。 |
| テスト/品質 | `test_data_register_tab_widget_status_tab.py` に、登録状況タブ表示中の親ウィンドウ縦リサイズでテーブル高さが増える回帰テストを追加。 |

## v2.5.33 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.33）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データ登録 | `data_register_tab_widget.py` で一括登録/登録状況/一覧/メール通知タブを lazy build 化。 |
| データ取得2 | `data_fetch2_tab_widget.py` で一括取得（RDE/DP）を lazy build 化し、フィルタタブは prewarm 付き lazy を維持。 |
| サブグループ/試料 | `subgroup_create_widget.py` の一覧タブ、`sample_dedup_tab_widget.py` の一覧2タブを遅延構築へ変更。 |
| 基本情報 | `basic_unified_status_widget.py` で 1 秒超過時の loading hint を追加。 |
| AI | `ui_ai_test.py` で AI設定/課題一覧の初期化 progress 表示を追加。 |
| データポータル一覧 | `dataset_listing_widget.py` で portal status キャッシュを即時適用し、全件強制更新は共通実装へ統一。 |
| テスト/品質 | `test_data_register_tab_widget_lazy_tabs.py`、`test_data_fetch2_bulk_tabs_lazy.py`、`test_basic_unified_status_widget_loading_hint.py`、`test_dataset_listing_widget_controls_and_auto_fetch.py` などを追加・更新。 |

## v2.5.32 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.32）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| 共通UI基盤 | `window_sizing.py` を追加し、最大化中はサイズ変更を抑止したうえで、通常時のメインウィンドウ再サイズ/横方向位置補正を共通化。 |
| データポータル | `data_portal_widget.py` でタブごとのウィンドウサイズ/位置を保存し、現在表示中タブだけをテーマ更新するよう改善。 |
| データポータル詳細 | `portal_listing_tab.py` / `dataset_upload_tab.py` / `portal_bulk_tab.py` の初期表示幅、背景スタイル、配色再適用を整理し、一覧/一括/データカタログの表示安定性を改善。 |
| AI/サブグループ/設定 | `ai_suggestion_dialog.py` の位置/タブ別サイズ保存、`subgroup_create_widget.py` の既存サブグループ読込セクション、設定タブのオフライン/起動時更新UIを整備。 |
| テスト/品質 | `test_window_sizing.py`、`test_data_portal_tab_window_state.py`、`test_data_portal_listing_tab_added.py`、`test_subgroup_create_tab_has_existing_load_section.py` などを追加・更新。 |

## v2.5.31 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.31）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データセット（新規開設/新規開設2） | `dataset_open_logic` で課題番号コンボの popup 表示前に発生していた `clear()` + `addItem()` の毎回再構築を廃止。 |
| データセット（課題番号候補） | 候補ペアをキャッシュし、`QStringListModel` + `QCompleter` を再利用して一覧表示の待ち時間を短縮。 |
| データセット（選択保持） | 空テキスト状態で一覧表示ボタンを押しても `currentData()` を維持し、選択値の取りこぼしを防止。 |
| テスト/品質 | `test_grant_combo_arrow_popup_preserves_current_selection_when_text_is_empty` を追加し、矢印クリック後の選択保持を回帰検証。 |

## v2.5.30 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.30）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データセット（新規開設/新規開設2） | `dataset_open_logic` で上位フィルタ変更時に下位フィルタ（課題番号/管理者）を初期化する制御を追加。 |
| データセット（課題番号初期選択） | サブグループ変更時に課題番号候補を即時再構築し、先頭候補を初期値として選択する挙動に統一。 |
| データセット（管理者初期選択） | 管理者コンボの再構築時に不整合保持を抑止し、初期選択を安定化。 |
| テスト/品質 | `test_dataset_open_filter_cascade_resets_to_first_defaults.py` を追加し、`test_dataset_open_filter_cascade_clear_invalid_selection.py` とあわせて回帰検証を強化。 |

## v2.5.29 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.29）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データポータル（操作対象表示） | `dataset_upload_tab.py` に環境名・対象サイトURLの共通確認メッセージ生成を追加し、主要操作の確認内容を統一。 |
| データポータル（公開URL） | `data_portal_public.py` で test 環境の公開URL生成時にポータル設定URLを優先し、`system_arim_data` 系URLを公開側URLへ正規化。 |
| データポータル（修正UI） | `portal_edit_dialog.py` に environment 引数を追加し、タイトル・保存確認へ反映。 |
| テスト/品質 | `tests/unit/test_dataset_upload_tab.py` に環境表示の確認を追加し、`tests/unit/utils/test_data_portal_public.py` に test URL導出の回帰テストを追加。 |

## v2.5.28 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.28）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| 基本情報（テンプレート再取得） | `basic_info_logic.fetch_template_info_from_api` で teamId 候補試行時のエラー分類を導入。 |
| 基本情報（失敗時停止制御） | 400/401 などの致命的HTTPエラーは以後の候補試行を停止し、再試行を抑制。 |
| 基本情報（通信失敗時停止制御） | 接続系エラーの連続発生時は候補巡回を停止し、待機時間の増幅を回避。 |
| テスト/品質 | `tests/unit/basic/test_dataset_chunk_fetch.py` に早期停止2ケースを追加し、回帰を検証。 |

## v2.5.27 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.27）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データセット（新規開設） | `dataset_open_logic` のロールフィルタ変更処理で、選択中サブグループが新条件外の場合に選択解除する安全側動作を追加。 |
| データセット（新規開設2） | `create_group_select_widget` 共通化経路で同じ不整合選択解除を適用し、新規開設2にも同等挙動を反映。 |
| データセット（下位フィルタ） | サブグループ再選択時、課題番号/管理者の前回選択を候補内のときのみ維持し、不一致時は解除。 |
| テスト/品質 | `test_dataset_open_filter_cascade_clear_invalid_selection.py` を追加し、ロール変更時の下位選択解除を回帰検証。 |

## v2.5.26 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.26）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データセット（統合タブ） | `dataset_open_widget` でタブ別ウィンドウサイズ保存/復元を追加し、タブ切替時のサイズ干渉を解消。 |
| データセット（新規開設2） | `dataset_open_logic` / `dataset_open_widget` のコンボ幅調整ポリシーを見直し、横スクロール過大化を抑制。 |
| データセット（閲覧・修正） | `dataset_edit_widget` で managed時サブグループフィルタを有効化し、候補を自己所属TEAMのみに限定。 |
| データセット（データエントリー） | `dataset_dataentry_widget_minimal` で managed時サブグループフィルタを有効化し、候補を自己所属TEAMのみに限定。 |
| テスト/品質 | `test_dataset_filter_mode_alignment` を更新し、managed時の有効状態/候補件数を回帰検証。 |

## v2.5.25 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.25）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データセット（新規開設2） | 既存データセット読込の表示対象を「管理（自身が開設・所有）/所属機関の課題/その他/全て」へ再編。 |
| データセット（新規開設2） | 既存データセット読込時、サブグループ未解決・権限不足ケースでサブグループ/課題/管理者選択を解除する安全側動作を追加。 |
| データセット（閲覧・修正） | 表示データセットのフィルタ区分を4区分へ統一し、ラベルを「サブグループフィルタ」「課題番号フィルタ」に統一。 |
| データセット（データエントリー） | 表示対象フィルタ区分を4区分へ統一し、サブグループフィルタ有効条件を閲覧・修正タブと同じ挙動に統一。 |
| データセット（共通） | サブグループフィルタ指定時、dataset.jsonにgroup関係が無い場合はdatasets/<id>.jsonのrelationships.groupをフォールバック参照。 |
| テスト/品質 | `test_dataset_filter_mode_alignment` などを追加・更新し、分類整合/有効条件/フォールバックを回帰検証。 |

## v2.5.24 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.24）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| サブグループ（閲覧・修正） | `subgroup_api_client` で Materialトークンを `TokenManager` 優先取得し、期限近接時の事前リフレッシュを追加。 |
| サブグループ（閲覧・修正） | `sample_extractor` の関連試料ダイアログにトークン状態ラベル（有効/期限切れ、残り時間、更新時刻）を追加。 |
| 設定（トークン状態） | `token_manager` の保存時に `rde-material.nims.go.jp` / `rde-material-api.nims.go.jp` を同期保存。 |
| 基本情報 | `basic_unified_status_widget` の個別取得UIを非表示化し、`ui_controller` で `状況更新` / `API Debug` を保存フォルダ行へ移設。 |
| テスト/品質 | `test_subgroup_material_token_refresh_status` / `test_related_samples_dialog_token_status` / `test_basic_info_ui` などを追加・更新。 |

## v2.5.23 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.23）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| サブグループ（閲覧・修正） | `subgroup_api_client` で Materialトークン保存呼び出しの引数順を修正（`save_bearer_token(token, host)`）。 |
| 設定（トークン状態） | `token_status_tab` の全トークンリフレッシュ対象を `ACTIVE_HOSTS` のみへ変更。 |
| 設定（トークン状態） | 全トークン確認ダイアログの件数表示を表示対象（2ホスト）に一致させるよう改善。 |
| テスト/品質 | `tests/unit/test_token_status_tab_refresh_all_targets.py` と `tests/unit/subgroup/test_subgroup_api_client_material_token_save_order.py` を追加。 |

## v2.5.22 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.22）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データポータル一覧 | `portal_listing_tab` の `_SourceAwareProxyModel` に `lessThan` を追加し、対象列で数値ソートを実装。 |
| データポータル一覧 | `ファイルサイズ` 列で `bytes/KB/MB/GB...` の単位換算比較を実装。 |
| データポータル一覧 | `code` 列で自然順ソート（数字部分を数値扱い）を実装。 |
| テスト/品質 | `test_portal_listing_proxy_column_filters` に3件のソート回帰テストを追加。 |

## v2.5.21 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.21）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| サブグループ（閲覧・修正） | `subgroup_edit_widget` のコンボボックスで、Completer候補クリック時に `setCurrentIndex` を即時反映する処理を追加。 |
| サブグループ（閲覧・修正） | 選択変更監視を `currentTextChanged` 依存から `currentIndexChanged` / `activated` へ拡張し、選択確定の取りこぼしを抑止。 |
| テスト/品質 | `test_subgroup_edit_combo_completer_selection_sync.py` を追加し、候補クリック・テキスト不変時の選択更新を自動検証。 |

## v2.5.20 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.20）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| サブグループ（新規作成） | `subgroup_member_selector_common` の表示フィルタ処理を修正し、表示対象行に対する重複マージ（同一メール1件化）を実装。 |
| サブグループ（新規作成） | `add_user_by_email` の重複判定を表示中行のみに変更し、フィルタ状態に応じた直接追加を可能化。 |
| サブグループ（新規作成） | `SubgroupCreateHandler` に作成条件の一括検証を追加し、未達条件を1回のメッセージで提示。 |
| テスト/品質 | `test_subgroup_member_selector_filter_consistency.py` などを更新し、表示フィルタ整合・重複統合・作成条件検証の回帰を追加。 |

## v2.5.19 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.19）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データポータル一覧 | `portal_entry_merge` と `portal_listing_tab` の補完経路を強化し、`managed:*` キー欠落時の補完注入に対応。 |
| データポータル一覧 | `portal_listing_tab` の `_SourceAwareProxyModel` で、対象列に対する日付/数値の範囲指定フィルタを実装。 |
| 公開データ抽出 | `data_portal_public` でフォーム型HTMLの抽出（DOI/複数dd/submit値）を改善。 |
| テスト/品質 | `test_portal_listing_proxy_column_filters` / `test_portal_listing_managed_fallback_values` / `test_data_portal_public` などを更新。 |

## v2.5.18 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.18）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データ登録（通常） | `data_register_ui_creator` でテンプレート解決結果を表示し、検証に解決済みテンプレートIDを適用。 |
| データ登録（一括） | `batch_register_widget` でテンプレート解決結果を表示し、ファイルセット必要拡張子にも解決済みテンプレートIDを適用。 |
| テンプレート解決 | `template_format_validator` に `resolve_template` / `get_template_reference_text` を追加。装置ID・版・日付で近似版を選択。 |
| テスト/品質 | `tests/unit/test_template_format_validator.py` にフォールバック/表示テストを追加。 |

## v2.5.17 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.17）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データポータル修正 | `dataset_upload_tab` の `t_code` 取得経路を `keyword=dataset_id` 検索方式へ変更。 |
| データポータル修正 | `portal_entry_status` の解析結果に `t_code` を追加し、hidden input から抽出。 |
| データポータル修正 | 現在選択dataset一致時は抽出済み `current_t_code` を優先再利用、未検出時は安全にクリア。 |
| テスト/品質 | `tests/unit/data_portal/test_portal_entry_status_parser.py` / `tests/unit/test_dataset_upload_tab.py` を更新。 |

## v2.5.16 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.16）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| オフラインモード | `offline_mode` コアを追加し、URL/AIアクセスのサイト別ブロック制御を実装。 |
| 設定UI | 設定タブに「オフライン」タブを追加し、有効化とサイト別対象の保存/反映に対応。 |
| 起動時制御 | オフライン起動時の確認、RDE接続異常時のオフライン移行提案を追加。 |
| 表示/UI | メイン画面に「📴 オフラインモード（対象: ...）」を表示。左メニュー遷移は許可し、通信処理時に制限。 |
| テスト/品質 | offline_mode / ui_controller / settings_offline_tab のテストを追加・更新。 |

## v2.5.15 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.15）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データ取得2 | 一括取得（DP）タブの検索をローカル `output/data_portal_public/output.json` 優先へ変更し、再検索時の遅延/タイムアウトを低減。 |
| データ取得2 | `dataset_id` 解決順を `fields_raw/fields.dataset_id` 優先へ修正し、RDEデータとの結合精度を向上。 |
| データ取得2 | dataEntry の metadata/included 参照による補完経路を追加し、登録者/試料（表示名）/試料（UUID）空欄を低減。 |
| テスト/品質 | bulk_dp_tab のウィジェットテストを拡充し、pytest段階ゲート→pre-build→PyInstaller運用を継続。 |

## v2.5.14 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.14）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データ取得2 | 一括取得（RDE）タブの取得列チェックで、クリック行以外への反映が起きる不安定挙動を抑止。 |
| データ取得2 | RDE検索インデックスのクエリキャッシュ永続化を追加し、再起動後の検索初速を改善。 |
| UI | 左ペイン「データ取得2」の未選択配色を専用グループ色へ修正し、他グループとの識別性を向上。 |
| テスト/品質 | unit/widget の回帰テストを拡充し、pytest段階ゲート→pre-build→PyInstaller運用を継続。 |

## v2.5.13 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.13）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データ取得2 | 一括取得（DP）タブでページングと並列フィルタ処理を改善。RDEタブのフィルタ反映と一覧更新の安定性を強化。 |
| テスト/品質 | 一括取得タブ関連のウィジェットテストを更新し、pytest段階ゲート→pre-build→PyInstaller運用を継続。 |

## v2.5.12 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.12）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データ取得2 | 一括取得（DP/RDE）タブのフィルタ候補・表示モード・検索導線を改善。DP検索の非同期化と操作状態制御を追加。 |
| テスト/品質 | 一括取得タブ関連のウィジェットテストを拡充し、pytest段階ゲート→pre-build→PyInstallerの運用を継続。 |

## v2.5.11 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.11）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データセット一覧 | 一覧設定の整理とUI部品の改善。ポータル公開状態キャッシュ連携と checked_at 補完を追加。 |

## v2.5.10 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.10）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| 配布 | 単一起動ガードの通知安定化と実行ファイル名解決を改善。Inno Setup スクリプトを整備。 |

## v2.5.9 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.9）。VERSION/README/配布物/ヘルプ/ドキュメントのバージョン表記を更新。 |
| データポータル | 一括/一覧タブの初期レイアウト適用、一覧タブの環境選択/自動更新、アップロード済みスキップを追加。 |

## v2.5.8 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.8）。VERSION/README/配布物/ヘルプのバージョン表記を更新。 |
| データポータル | 一括タブの列/フィルタ/実施機関マッピング/JSON状態表示を改善。 |

## v2.5.7 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.7）。VERSION/README/配布物/ヘルプのバージョン表記を更新。 |
| テスト/品質 | pytest 段階ゲート → pre-build（Non-Widget/Widget + coverage）→ PyInstaller の段階ゲートを完走し、回帰を抑止。 |

## v2.5.6 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.6）。VERSION/README/配布物/ヘルプのバージョン表記を更新。 |
| テスト/品質 | pytest 段階ゲート → pre-build（Non-Widget/Widget + coverage）→ PyInstaller の段階ゲートを完走し、回帰を抑止。 |

## v2.5.5 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.5）。VERSION/README/配布物/ヘルプのバージョン表記を更新。 |
| AI説明文提案 | AI拡張/データセット/報告書タブのレイアウトを改善（上下2ペイン・条件付きスクロール・表示行数固定）。 |
| テスト/品質 | pytest 段階ゲート → pre-build（Non-Widget/Widget + coverage）→ PyInstaller の段階ゲートを完走し、回帰を抑止。 |

## v2.5.4 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.4）。VERSION/README/配布物/ヘルプのバージョン表記を更新。 |
| テスト/品質 | pytest 段階ゲート → pre-build（Non-Widget/Widget + coverage）→ PyInstaller の段階ゲートを完走し、回帰を抑止。 |

## v2.5.3 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.3）。VERSION/README/配布物/ヘルプのバージョン表記を更新。 |
| テスト/品質 | pytest 段階ゲート → pre-build（Non-Widget/Widget + coverage）→ PyInstaller の段階ゲートを完走し、回帰を抑止。 |

## v2.5.2 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.2）。VERSION/README/配布物/ヘルプのバージョン表記を更新。 |
| テスト/品質 | pytest 段階ゲート → pre-build（Non-Widget/Widget + coverage）→ PyInstaller の段階ゲートを完走し、回帰を抑止。 |

## v2.5.1 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.1）。VERSION/README/配布物/ヘルプのバージョン表記を更新。 |
| テスト/品質 | pytest 段階ゲート → pre-build（Non-Widget/Widget + coverage）→ PyInstaller の段階ゲートを完走し、回帰を抑止。 |

## v2.5.0 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.5.0）。VERSION/README/配布物のバージョン表記を更新。 |
| テスト/品質 | pre-build（Non-Widget/Widget + coverage）を通過するようユニットテストとゲート運用を安定化。 |

## v2.4.23 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.4.23）。VERSION/README/配布物のバージョン表記を更新。 |
| テスト/品質 | pytest 段階ゲート → pre-build 統合テスト → PyInstaller ビルドを実行して回帰を抑止。 |

## v2.4.22 の主な更新点

| 分類 | 内容 |
| --- | --- |
| データエントリー編集 | 既存試料名の選択肢を追加し、モードに応じてUUID欄の入力可否を切替。 |
| UX | 既存試料選択時のUUID欄を表示専用にし、誤入力を抑止。 |

## v2.4.15 の主な更新点

| 分類 | 内容 |
| --- | --- |
| 更新 | 更新ダウンロードの通信ログをダイアログに表示し、失敗時の切り分けを容易化。 |
| 更新 | bytes ベースの進捗更新に統一し、Content-Length 不明でも「固まって見える」状況を緩和。 |
| 安定性 | 更新ダイアログのUI更新を Signal/QueuedConnection 経由に統一し、スレッド跨ぎの Qt クラッシュを抑止。 |
| UX | インストーラ起動時に「更新のため終了（クラッシュではない）」メッセージを表示。 |
| テスト/品質 | ユニット/ウィジェット/統合テストを実行して回帰を抑止。 |

## v2.4.14 の主な更新点

| 分類 | 内容 |
| --- | --- |
| データセット一覧 | ポータル列の公開状態表示を改善（公開JSON補完/ログインCSV一括判定/セルクリック再確認+セル内スピナー）。 |
| パフォーマンス | 個別アクセス回数を抑制（キャッシュの1日維持・上書き保存、クリック時のみ再確認）。 |
| テスト/品質 | ユニット/ウィジェット/統合テストを実行して回帰を抑止。 |

## v2.4.13 の主な更新点

| 分類 | 内容 |
| --- | --- |
| データセット一覧 | 範囲フィルタ群を2行表示に変更し、視認性を改善。 |
| フィルタ | TAG数の範囲フィルタが絞り込みに反映されない不具合を修正。 |
| データ整合 | file_size は bytes(int) を保持し、エクスポートも bytes を出力するよう統一。 |
| テスト/品質 | ユニット/ウィジェット/統合テストを実行して回帰を抑止。 |

## v2.4.12 の主な更新点

| 分類 | 内容 |
| --- | --- |
| 一覧タブ | 大規模データで固まって見える（無限スピナー）ケースを抑止するため、一覧生成の重い処理を抑制。 |
| 安定性 | 一覧タブの非同期リロードで QThread の寿命管理を改善し、タブ切替等での破棄競合を抑止。 |
| テスト/品質 | ユニット/ウィジェット/統合テストを実行して回帰を抑止。 |

## v2.4.11 の主な更新点

| 分類 | 内容 |
| --- | --- |
| サブグループ一覧 | 複数要素の改行表示、関連データ/試料の個別リンク、長文省略+ツールチップを改善。 |
| UI/可読性 | 行高さを明示制御し、過大な余白で1行しか見えない問題を抑制。 |
| フィルタUI | 範囲フィルタの折り返し時にラベルが重なって見える問題を修正。 |
| テスト/品質 | ユニット/ウィジェット/統合テストを実行して回帰を抑止。 |

## v2.4.10 の主な更新点

| 分類 | 内容 |
| --- | --- |
| データセット一覧 | 範囲フィルタの1行化（「～」表記）・フィルタ領域の折りたたみ（要約表示）を追加。 |
| パフォーマンス | 一覧生成のインメモリキャッシュにより表示を高速化。 |
| エクスポート | CSV/XLSXエクスポートで日時付きの既定ファイル名を保存ダイアログにサジェスト。 |
| テスト/品質 | ユニット/ウィジェット/統合テストを実行して回帰を抑止。 |

## v2.4.9 の主な更新点

| 分類 | 内容 |
| --- | --- |
| リリース/品質 | リビジョンアップ（v2.4.9）。REVISION/VERSION.txt/README/ヘルプのバージョン表記を統一。 |
| ドキュメント | 実装と整合するようドキュメントを更新し、古いリリースノート/旧ドキュメントをアーカイブへ退避。 |
| テスト | ユニット/ウィジェット/統合テストを実行して回帰を抑止。 |

## v2.4.8 の主な更新点

| 分類 | 内容 |
| --- | --- |
| AI | AI説明文提案ダイアログの「報告書」タブを拡張し、横断技術領域（主/副）の列表示と事前フィルタに対応。 |
| AI | 結果一覧タブ（対象=報告書）で、年度/機関コード/横断/重要（主/副）列の表示と絞り込みを追加。 |
| AI/品質 | 報告書ログの target_key が課題番号のみの場合でも converted.xlsx と結合して値を補完し、空欄を抑制。 |
| テスト/品質 | 上記 UI のウィジェットテストを更新し、回帰を防止。 |

## v2.4.7 の主な更新点

| 分類 | 内容 |
| --- | --- |
| 設定/メール | メールタブの非機微設定（From/SMTP host等）を OS キーチェーンへ退避し、上書きインストール等で設定JSONが初期化されても自動復元できるように改善。 |
| UI | 設定画面の MISC タブをタブ一覧の最後尾へ移動。 |
| 更新 | MISC タブのアプリ更新後に自動で再起動するフローを追加（インストーラ完了待ち→再起動を別プロセスへ委譲）。 |
| テスト/品質 | Windows + PySide6 + pytest-qt の長時間実行で発生し得るクラッシュを回避するため、描画監視のイベントフックをroot配下に限定して安定化。 |

## v2.4.6 の主な更新点

| 分類 | 内容 |
| --- | --- |
| テスト/品質 | Windows + PySide6 + pytest-qt 環境での長時間スイート実行を安定化するため、待機処理/実行手順を見直し。 |
| テスト/運用 | フルスイートを「非widget → widget」に分割して実行できるようにし、単一コマンドでの完走性を改善。 |
| ドキュメント | VERSION/README/ヘルプのバージョン表記を v2.4.6 に更新。 |

## v2.4.5 の主な更新点

| 分類 | 内容 |
| --- | --- |
| テスト/品質 | 統合テストでの patch 互換性を維持するため、フォーム生成関数の公開API（モジュールレベル）を復旧。 |
| データセット | 起動ペイロードが先着した場合でもデータセット事前選択が外れないよう、初期ロードと受信登録タイミングを調整。 |
| パス管理 | 診断ユーティリティのパス解決で CWD 依存を排除し、動的パス解決へ統一。 |
| テーマ | スプラッシュ画面の文字色の直書きを廃止し、テーマキーから取得するよう改善。 |

## v2.4.4 の主な更新点

| 分類 | 内容 |
| --- | --- |
| データ取得2 | メール通知タブ: 対象通知リストのフィルタを自動通知の送信対象にも適用（表示されていないものは送信しない）。 |
| データ取得2 | メール通知タブ: 「通知対象抽出」で最新情報取得も同時に行うオプションを追加。 |
| データ取得2 | メール通知タブ: 基準日時に「自動（現在）/直接指定」モードを追加。 |
| データ取得2 | メール通知タブ: 削除テンプレが再起動で復活する不具合を抑止。 |

## v2.4.3 の主な更新点

| 分類 | 内容 |
| --- | --- |
| データ取得2 | メール通知タブの運用を改善（運用モード表示の簡略化、本番送信先に設備管理者を追加）。 |

## v2.4.2 の主な更新点

| 分類 | 内容 |
| --- | --- |
| データ取得2 | メール通知タブを拡張（テンプレ編集の分離、宛先選択の明確化、送信ログ運用の改善、設備管理者プレースホルダ対応）。 |
| 設備 | 設備管理者（設備IDごと）の編集・永続化UIを追加し、装置名フォールバック補完と表示不具合を修正。 |

## v2.4.1 の主な更新点

| 分類 | 内容 |
| --- | --- |
| データ取得2 | メール通知タブを改善（運用モード: テスト/本番、送信先: 投入者/所有者/両方、抽出範囲プリセット、送信ログ閲覧）。 |
| メール | Gmail/SMTPのFrom表示名（任意）を追加し、送信ヘッダへ反映。 |

## v2.4.0 の主な更新点

| 分類 | 内容 |
| --- | --- |
| データ登録 | 「登録状況」タブを拡張し、自動確認（10秒ポーリング）・進捗可視化・停止トグル・リンク列縮小・水平スクロール対応・追加列（投入者/所有者/エラー情報）を実装。 |
| パフォーマンス | 大量行でも固まりにくいよう、キャッシュ読込の非同期化とセルクリック方式へ最適化。 |
| UI/UX | 登録状況タブで発生していたウィンドウ固定幅化を解消し、リサイズ可能に修正。 |
