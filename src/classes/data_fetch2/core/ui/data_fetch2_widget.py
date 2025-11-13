#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
データ取得2ウィジェット v1.17.2
データセット選択・ファイル一括取得機能

主要機能:
- dataset.json参照による検索付きドロップダウン
- 選択データセットのファイル一括取得
- プログレス表示対応
- 企業プロキシ・SSL証明書対応

変更履歴:
- v1.17.2: フィルタリングロジック完全修正・ドロップダウンUI改善
- v1.15.1: プロキシ設定UI改善、PAC・企業CA設定の横並び表示対応
- v1.15.0: ワークスペース整理完了・コードベース品質向上
"""

import os
import logging
import threading
import json
from qt_compat.widgets import QVBoxLayout, QLabel, QWidget, QMessageBox, QProgressDialog, QComboBox, QPushButton
from qt_compat.core import QTimer, Qt, QMetaObject, Q_ARG, QUrl
from qt_compat.gui import QDesktopServices
from config.common import OUTPUT_DIR, DATAFILES_DIR

# ロガー設定
logger = logging.getLogger(__name__)

def safe_show_message_widget(parent, title, message, message_type="warning"):
    """
    スレッドセーフなメッセージ表示（ウィジェット用）
    """
    if parent is None:
        return
    
    try:
        def show_message():
            if message_type == "warning":
                QMessageBox.warning(parent, title, message)
            elif message_type == "critical":
                QMessageBox.critical(parent, title, message)
            elif message_type == "information":
                QMessageBox.information(parent, title, message)
        
        # メインスレッドで実行
        QTimer.singleShot(0, show_message)
        
    except Exception as e:
        logger.error(f"メッセージボックス表示エラー: {e}")
        logger.error(f"[{message_type.upper()}] {title}: {message}")

def create_dataset_dropdown_all(dataset_json_path, parent, global_share_filter="both"):
    """
    データセットドロップダウンを作成（データ取得2専用版・フィルタリング対応）
    dataset_dropdown_util.py の実装を参考に完全なフィルタリング機能を提供
    """
    import json
    import os
    from qt_compat.widgets import QWidget, QVBoxLayout, QComboBox, QLabel, QHBoxLayout, QRadioButton, QLineEdit, QPushButton, QButtonGroup, QCompleter
    from qt_compat.core import Qt
    
    def check_global_sharing_enabled(dataset_item):
        """広域シェアが有効かどうかをチェック"""
        global_share = dataset_item.get("attributes", {}).get("globalShareDataset")
        # データ構造確認結果：globalShareDatasetは通常Noneまたは未定義
        # 実際のシェア状況は別の属性で判定する必要がある可能性
        # ひとまず isOpen を使用（公開されているかどうか）
        is_open = dataset_item.get("attributes", {}).get("isOpen", False)
        return is_open  # isOpenをglobalShareの代替として使用
    
    def get_current_user_id():
        """現在のユーザーIDを取得"""
        from config.common import get_dynamic_file_path
        try:
            self_path = get_dynamic_file_path("output/rde/data/self.json")
            if os.path.exists(self_path):
                with open(self_path, 'r', encoding='utf-8') as f:
                    self_data = json.load(f)
                return self_data.get("data", {}).get("id", "")
        except Exception:
            return ""
        return ""
    
    def check_user_is_member(dataset_item, user_id):
        """ユーザーがデータセットのメンバーかどうかをチェック"""
        if not user_id:
            return False
        
        # relationshipsからメンバー情報を確認
        # データ構造確認結果：membersキーは存在しない
        # 代替として manager, dataOwners, applicant を確認
        relationships = dataset_item.get("relationships", {})
        
        # managerId確認
        manager = relationships.get("manager", {}).get("data", {})
        if isinstance(manager, dict) and manager.get("id") == user_id:
            return True
        
        # dataOwners確認
        data_owners = relationships.get("dataOwners", {}).get("data", [])
        if isinstance(data_owners, list):
            for owner in data_owners:
                if isinstance(owner, dict) and owner.get("id") == user_id:
                    return True
        
        # applicant確認
        applicant = relationships.get("applicant", {}).get("data", {})
        if isinstance(applicant, dict) and applicant.get("id") == user_id:
            return True
        
        return False
    
    def check_dataset_type_match(dataset_item, dataset_type_filter):
        """データセットタイプがフィルタにマッチするかチェック"""
        if dataset_type_filter == "all":
            return True
        
        dataset_type = dataset_item.get("attributes", {}).get("datasetType", "")
        return dataset_type == dataset_type_filter
    
    def check_grant_number_match(dataset_item, grant_number_filter):
        """課題番号がフィルタにマッチするかチェック"""
        if not grant_number_filter:
            return True
        
        grant_number = dataset_item.get("attributes", {}).get("grantNumber", "")
        return grant_number_filter.lower() in grant_number.lower()
    
    def get_dataset_type_display_map():
        """データセットタイプの表示マップを取得"""
        return {
            "ANALYSIS": "解析",
            "RECIPE": "レシピ",
            "MEASUREMENT": "測定",
            "SIMULATION": "シミュレーション",
            "OTHERS": "その他"
        }
    
    # メインコンテナ
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    
    # フィルタ（1行にまとめる）
    filter_widget = QWidget()
    filter_layout = QHBoxLayout()
    filter_layout.setContentsMargins(0, 0, 0, 0)
    
    # 広域シェア設定フィルタ
    share_label = QLabel("広域シェア設定:")
    share_label.setStyleSheet("font-weight: bold;")
    
    share_both_radio = QRadioButton("両方")
    share_enabled_radio = QRadioButton("有効のみ")
    share_disabled_radio = QRadioButton("無効のみ")
    share_both_radio.setChecked(True)  # デフォルト
    
    share_button_group = QButtonGroup()
    share_button_group.addButton(share_both_radio, 0)
    share_button_group.addButton(share_enabled_radio, 1)
    share_button_group.addButton(share_disabled_radio, 2)
    
    filter_layout.addWidget(share_label)
    filter_layout.addWidget(share_both_radio)
    filter_layout.addWidget(share_enabled_radio)
    filter_layout.addWidget(share_disabled_radio)
    
    # スペーサー
    filter_layout.addSpacing(20)
    
    # 関係メンバーフィルタ
    member_label = QLabel("関係メンバー:")
    member_label.setStyleSheet("font-weight: bold;")
    
    member_both_radio = QRadioButton("両方")
    member_only_radio = QRadioButton("メンバーのみ")
    member_non_radio = QRadioButton("非メンバーのみ")
    member_both_radio.setChecked(True)  # デフォルト
    
    member_button_group = QButtonGroup()
    member_button_group.addButton(member_both_radio, 0)
    member_button_group.addButton(member_only_radio, 1)
    member_button_group.addButton(member_non_radio, 2)
    
    filter_layout.addWidget(member_label)
    filter_layout.addWidget(member_both_radio)
    filter_layout.addWidget(member_only_radio)
    filter_layout.addWidget(member_non_radio)
    filter_layout.addStretch()
    
    filter_widget.setLayout(filter_layout)
    layout.addWidget(filter_widget)
    
    # データセットタイプフィルタ
    type_widget = QWidget()
    type_layout = QHBoxLayout()
    type_layout.setContentsMargins(0, 0, 0, 0)
    
    type_label = QLabel("データセットタイプ:")
    type_label.setMinimumWidth(120)
    type_label.setStyleSheet("font-weight: bold;")
    
    type_combo = QComboBox()
    type_combo.addItem("全て", "all")
    type_display_map = get_dataset_type_display_map()
    for dtype, label in type_display_map.items():
        type_combo.addItem(label, dtype)
    type_combo.setMinimumWidth(150)
    
    type_layout.addWidget(type_label)
    type_layout.addWidget(type_combo)
    type_layout.addStretch()
    
    type_widget.setLayout(type_layout)
    layout.addWidget(type_widget)
    
    # 課題番号フィルタ
    grant_widget = QWidget()
    grant_layout = QHBoxLayout()
    grant_layout.setContentsMargins(0, 0, 0, 0)
    
    grant_label = QLabel("課題番号:")
    grant_label.setMinimumWidth(120)
    grant_label.setStyleSheet("font-weight: bold;")
    
    grant_edit = QLineEdit()
    grant_edit.setPlaceholderText("部分一致で検索（例: JPMXP1234）")
    grant_edit.setMinimumWidth(300)
    
    grant_layout.addWidget(grant_label)
    grant_layout.addWidget(grant_edit)
    grant_layout.addStretch()
    
    grant_widget.setLayout(grant_layout)
    layout.addWidget(grant_widget)
    
    # 表示件数ラベル
    count_label = QLabel("表示中: 0/0 件")
    count_label.setStyleSheet("color: #666; font-size: 10pt; font-weight: bold;")
    layout.addWidget(count_label)
    
    # データセット検索フィールド
    search_widget = QWidget()
    search_layout = QHBoxLayout()
    search_layout.setContentsMargins(0, 0, 0, 0)
    
    search_label = QLabel("データセット名・課題番号・タイトルで検索:")
    search_label.setStyleSheet("font-weight: bold;")
    search_edit = QLineEdit()
    search_edit.setPlaceholderText("リストから選択、またはキーワードで検索して選択してください")
    search_edit.setMinimumWidth(400)
    
    search_layout.addWidget(search_label)
    #search_layout.addWidget(search_edit)
    
    search_widget.setLayout(search_layout)
    layout.addWidget(search_widget)
    
    # コンボボックス作成
    combo = QComboBox()
    combo.setMinimumWidth(650)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setMaxVisibleItems(15)
    combo.lineEdit().setPlaceholderText("データセットを選択してください")
    
    combo.setStyleSheet("""
        QComboBox {
            border: 2px solid #2196F3;
            border-radius: 6px;
            padding: 8px;
            font-size: 11pt;
            min-height: 25px;
            padding-right: 35px;
        }
        QComboBox:focus {
            border-color: #1976D2;
            background-color: #E3F2FD;
        }
        QComboBox:hover {
            border-color: #1565C0;
            background-color: #F5F5F5;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 30px;
            border-left: 1px solid #2196F3;
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
            background-color: #2196F3;
        }
        QComboBox::drop-down:hover {
            background-color: #1976D2;
        }
        QComboBox::down-arrow {
            width: 0;
            height: 0;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 8px solid white;
            margin: 0px;
        }
        QComboBox::down-arrow:on {
            border-top: 8px solid #E3F2FD;
        }
    """)
    
    # 全件表示ボタン（コンボボックスの隣に配置）
    combo_container = QWidget()
    combo_layout = QHBoxLayout()
    combo_layout.setContentsMargins(0, 0, 0, 0)
    
    show_all_btn = QPushButton("全件表示")
    #show_all_btn.setMaximumWidth(80)
    #show_all_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; border-radius: 4px; padding: 5px;")
    
    combo_layout.addWidget(combo)
    #combo_layout.addWidget(show_all_btn)
    combo_container.setLayout(combo_layout)
    
    layout.addWidget(combo_container)
    
    def load_and_filter_datasets():
        """フィルタリング設定を適用してコンボボックスを更新"""
        try:
            # フィルタ設定を取得
            share_filter_types = {0: "both", 1: "enabled", 2: "disabled"}
            member_filter_types = {0: "both", 1: "member", 2: "non_member"}
            
            share_filter_type = share_filter_types.get(share_button_group.checkedId(), "both")
            member_filter_type = member_filter_types.get(member_button_group.checkedId(), "both")
            dtype_filter = type_combo.currentData() or "all"
            grant_filter = grant_edit.text().strip()
            
            # dataset.jsonからデータを読み込み
            if not os.path.exists(dataset_json_path):
                logger.warning("dataset.json が見つかりません: %s", dataset_json_path)
                combo.clear()
                combo.addItem("-- データセット情報がありません --", None)
                count_label.setText("表示中: 0/0 件")
                return
            
            with open(dataset_json_path, 'r', encoding='utf-8') as f:
                dataset_data = json.load(f)
            
            # データセットリストを取得（data配下かルート配下かを判定）
            if isinstance(dataset_data, dict) and 'data' in dataset_data:
                dataset_items = dataset_data['data']
            elif isinstance(dataset_data, list):
                dataset_items = dataset_data
            else:
                dataset_items = []
            
            # 現在のユーザーIDを取得
            current_user_id = get_current_user_id()
            
            # フィルタリング処理
            filtered_datasets = []
            total_count = len(dataset_items)
            
            for dataset in dataset_items:
                if not isinstance(dataset, dict):
                    continue
                
                # 広域シェアフィルタの適用
                is_global_share_enabled = check_global_sharing_enabled(dataset)
                if share_filter_type == "enabled" and not is_global_share_enabled:
                    continue
                elif share_filter_type == "disabled" and is_global_share_enabled:
                    continue
                
                # メンバーシップフィルタの適用
                is_user_member = check_user_is_member(dataset, current_user_id) if current_user_id else False
                if member_filter_type == "member" and not is_user_member:
                    continue
                elif member_filter_type == "non_member" and is_user_member:
                    continue
                
                # データセットタイプフィルタの適用
                if not check_dataset_type_match(dataset, dtype_filter):
                    continue
                
                # 課題番号フィルタの適用
                if not check_grant_number_match(dataset, grant_filter):
                    continue
                
                filtered_datasets.append(dataset)
            
            # コンボボックスを更新
            combo.clear()
            combo.addItem("-- データセットを選択してください --", None)
            
            display_list = ["-- データセットを選択してください --"]
            
            for dataset in filtered_datasets:
                attrs = dataset.get("attributes", {})
                dataset_id = dataset.get("id", "")
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                dataset_type = attrs.get("datasetType", "")
                subject_title = attrs.get("subjectTitle", "")
                
                # データセットタイプの日本語表示
                type_display = type_display_map.get(dataset_type, dataset_type) if dataset_type else ""
                
                # 広域シェア状態とメンバーシップ状態の表示
                share_status = "🌐" if is_global_share_enabled else "🔒"
                member_status = "👤" if is_user_member else "👥"
                
                # 表示文字列を構築
                display_parts = []
                if grant_number:
                    display_parts.append(grant_number)
                if subject_title:
                    display_parts.append(f"{subject_title[:30]}...")
                display_parts.append(name[:40] + ("..." if len(name) > 40 else ""))
                
                if type_display:
                    display_parts.append(f"[{type_display}]")
                
                display_text = f"{share_status}{member_status} {' '.join(display_parts)}"
                
                combo.addItem(display_text, dataset_id)
                display_list.append(display_text)
            
            # QCompleter設定
            completer = QCompleter(display_list, combo)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            combo.setCompleter(completer)
            
            # 件数表示を更新
            filtered_count = len(filtered_datasets)
            count_label.setText(f"表示中: {filtered_count}/{total_count} 件")
            
            logger.info("データセットフィルタリング完了: 広域シェア=%s, メンバー=%s, タイプ=%s, 課題番号='%s', 結果=%s/%s件", share_filter_type, member_filter_type, dtype_filter, grant_filter, filtered_count, total_count)
            
        except Exception as e:
            logger.error("データセット読み込みエラー: %s", e)
            combo.clear()
            combo.addItem("-- データセット読み込みエラー --", None)
            count_label.setText("表示中: 0/0 件")
            import traceback
            traceback.print_exc()
    
    def show_all_datasets():
        """全件表示ボタンが押された時の処理"""
        # すべてのフィルタを「両方」「全て」に設定
        share_button_group.button(0).setChecked(True)  # 両方
        member_button_group.button(0).setChecked(True)  # 両方
        type_combo.setCurrentIndex(0)  # 全て
        grant_edit.clear()  # 課題番号フィルタをクリア
        search_edit.clear()  # 検索フィールドもクリア
        
        # フィルタ適用
        load_and_filter_datasets()
        
        # コンボボックスを展開して全件表示
        combo.showPopup()
    
    # フィルタ変更時のイベント接続（PySide6: [int]シグネチャ削除）
    share_button_group.buttonClicked.connect(lambda: load_and_filter_datasets())
    member_button_group.buttonClicked.connect(lambda: load_and_filter_datasets())
    type_combo.currentTextChanged.connect(lambda: load_and_filter_datasets())
    grant_edit.textChanged.connect(lambda: load_and_filter_datasets())
    
    # 全件表示ボタンのイベント接続
    show_all_btn.clicked.connect(show_all_datasets)
    
    # 検索フィールドとコンボボックスの連携
    search_edit.textChanged.connect(lambda text: combo.lineEdit().setText(text))
    combo.lineEdit().textChanged.connect(lambda text: search_edit.setText(text))
    
    # 初回読み込み
    load_and_filter_datasets()
    
    # コンテナの属性設定
    container.dataset_dropdown = combo
    container.share_button_group = share_button_group
    container.member_button_group = member_button_group
    container.type_combo = type_combo
    container.grant_edit = grant_edit
    container.search_edit = search_edit
    container.count_label = count_label
    
    return container

def create_data_fetch2_widget(parent=None, bearer_token=None):
    # 非同期化を解除（QThread, Workerクラス削除）
    """
    データ取得2用ウィジェット（dataset.json参照・検索付きドロップダウン）
    """
    widget = QWidget(parent)
    layout = QVBoxLayout(widget)

    # dataset.jsonのパス
    dataset_json_path = os.path.normpath(os.path.join(OUTPUT_DIR, 'rde/data/dataset.json'))

    # dataset.jsonの絶対パスを表示
    dataset_json_abspath = os.path.abspath(dataset_json_path)

    path_label = QLabel(f"dataset.jsonパス: {dataset_json_abspath}")
    path_label.setStyleSheet("color: #888; font-size: 9pt; padding: 0px 0px;")
    layout.addWidget(path_label)

    # 広域シェアフィルタ付きデータセットドロップダウンを作成
    fetch2_dropdown_widget = create_dataset_dropdown_all(dataset_json_path, widget, global_share_filter="both")
    layout.addWidget(fetch2_dropdown_widget)

    # 選択中データセットのファイルリストを取得するボタン
    fetch_files_btn = QPushButton("選択したデータセットのファイルを一括取得")
    fetch_files_btn.setStyleSheet(
        "background-color: #1976d2; color: white; font-weight: bold; font-size: 13px; padding: 8px 16px; border-radius: 6px;"
    )
    layout.addWidget(fetch_files_btn)

    # エクスプローラーでdataFilesフォルダを開くボタン
    open_folder_btn = QPushButton("出力フォルダ(dataFiles)をエクスプローラーで開く")
    layout.addWidget(open_folder_btn)

    def on_open_folder():
        QDesktopServices.openUrl(QUrl.fromLocalFile(DATAFILES_DIR))

    open_folder_btn.clicked.connect(on_open_folder)




    def on_fetch_files():
        """ファイル取得ボタンのクリックハンドラ"""
        try:
            # ドロップダウンから選択データセットID取得
            combo = getattr(fetch2_dropdown_widget, 'dataset_dropdown', None)
            if combo is None:
                logger.error("ドロップダウンが見つかりません")
                safe_show_message_widget(widget, "エラー", "ドロップダウンが見つかりません", "warning")
                return

            idx = combo.currentIndex()
            dataset_id = combo.itemData(idx)
            logger.info(f"選択されたデータセット: index={idx}, dataset_id={dataset_id}")

            # データセットが選択されているかチェック
            if dataset_id is None or not dataset_id:
                logger.warning("データセットが選択されていません")
                safe_show_message_widget(widget, "選択エラー", "データセットを選択してください。", "warning")
                return
            
            # dataset.jsonからデータセット情報を取得
            try:
                with open(dataset_json_path, 'r', encoding='utf-8') as f:
                    dataset_data = json.load(f)
                
                # データセットリストを取得
                if isinstance(dataset_data, dict) and 'data' in dataset_data:
                    dataset_items = dataset_data['data']
                elif isinstance(dataset_data, list):
                    dataset_items = dataset_data
                else:
                    dataset_items = []
                
                # 選択されたデータセットIDに対応するオブジェクトを検索
                dataset_obj = None
                for dataset in dataset_items:
                    if dataset.get('id') == dataset_id:
                        dataset_obj = dataset
                        break
                
                if dataset_obj is None:
                    logger.error(f"データセットオブジェクトが見つかりません: {dataset_id}")
                    safe_show_message_widget(widget, "データセットエラー", f"データセットオブジェクトが見つかりません: {dataset_id}", "warning")
                    return
                    
            except Exception as e:
                logger.error(f"データセット情報取得エラー: {e}")
                safe_show_message_widget(widget, "データセット情報エラー", f"データセット情報の取得に失敗しました: {e}", "warning")
                return

            # Bearer Token統一管理システムで取得
            from core.bearer_token_manager import BearerTokenManager
            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
            if not bearer_token:
                logger.error("認証トークンが取得できません")
                safe_show_message_widget(widget, "認証エラー", "認証トークンが取得できません。ログインを確認してください。", "warning")
                return

            # プログレス表示付きでファイル取得処理を実行
            def show_fetch_progress():
                """プログレス表示付きファイル取得"""
                try:
                    from qt_compat.widgets import QProgressDialog, QMessageBox
                    from qt_compat.core import QTimer, Qt
                    from classes.utils.progress_worker import ProgressWorker
                    from classes.data_fetch2.core.logic.fetch2_filelist_logic import fetch_files_json_for_dataset
                    import threading
                    
                    # プログレスダイアログ作成
                    progress_dialog = QProgressDialog(widget)
                    progress_dialog.setWindowTitle("ファイルリスト取得")
                    progress_dialog.setLabelText("処理を開始しています...")
                    progress_dialog.setRange(0, 100)
                    progress_dialog.setValue(0)
                    progress_dialog.setWindowModality(Qt.WindowModal)
                    progress_dialog.setCancelButtonText("キャンセル")
                    progress_dialog.show()
                    
                    # ワーカー作成（ProgressWorkerを使用）
                    # フィルタ設定を取得（親タブウィジェットから）
                    file_filter_config = None
                    try:
                        # 親オブジェクトがDataFetch2TabWidgetの場合、フィルタ設定を取得
                        parent_obj = widget.parent()
                        while parent_obj:
                            if hasattr(parent_obj, 'current_filter_config'):
                                file_filter_config = parent_obj.current_filter_config
                                logger.info(f"フィルタ設定を取得: {file_filter_config}")
                                break
                            parent_obj = parent_obj.parent()
                    except Exception as e:
                        logger.warning(f"フィルタ設定取得エラー（デフォルトフィルタを使用）: {e}")
                    
                    # デフォルトフィルタにフォールバック
                    if not file_filter_config:
                        try:
                            from classes.data_fetch2.conf.file_filter_config import get_default_filter
                            file_filter_config = get_default_filter()
                            logger.info(f"デフォルトフィルタを使用: {file_filter_config}")
                        except ImportError:
                            file_filter_config = {"file_types": ["MAIN_IMAGE"]}
                            logger.info("基本フィルタを使用: MAIN_IMAGE のみ")
                    
                    worker = ProgressWorker(
                        fetch_files_json_for_dataset,
                        task_args=[widget, dataset_obj, bearer_token],
                        task_kwargs={"save_dir": None, "file_filter_config": file_filter_config},
                        task_name="ファイルリスト取得"
                    )
                    
                    # プログレス更新の接続
                    def update_progress(value, message):
                        def set_progress():
                            if progress_dialog and not progress_dialog.wasCanceled():
                                progress_dialog.setValue(value)
                                progress_dialog.setLabelText(message)
                        QTimer.singleShot(0, set_progress)
                    
                    # 完了時の処理
                    def on_finished(success, message):
                        def handle_finished():
                            if progress_dialog:
                                progress_dialog.close()
                            if success:
                                logger.info(f"ファイル取得処理完了: dataset_id={dataset_obj}")
                                if message and message != "no_data":
                                    safe_show_message_widget(widget, "完了", message, "information")
                                elif message == "no_data":
                                    safe_show_message_widget(widget, "情報", "選択されたデータセットにはデータエントリがありませんでした", "information")
                                else:
                                    safe_show_message_widget(widget, "完了", "ファイルリスト取得が完了しました", "information")
                            else:
                                logger.error(f"ファイル取得処理失敗: dataset_id={dataset_obj}, error={message}")
                                error_msg = message if message else "ファイル取得中にエラーが発生しました"
                                safe_show_message_widget(widget, "エラー", error_msg, "critical")
                        QTimer.singleShot(0, handle_finished)
                    
                    # キャンセル処理
                    def on_cancel():
                        worker.cancel()
                        logger.info("ファイル取得処理がキャンセルされました")
                        if progress_dialog:
                            progress_dialog.close()
                    
                    worker.progress.connect(update_progress)
                    worker.finished.connect(on_finished)
                    progress_dialog.canceled.connect(on_cancel)
                    
                    # バックグラウンドスレッドで実行
                    def run_worker():
                        try:
                            worker.run()
                        except Exception as e:
                            logger.error(f"ワーカー実行中にエラー: {e}")
                            import traceback
                            traceback.print_exc()
                            # エラー時の処理をメインスレッドで実行
                            def handle_error():
                                if progress_dialog:
                                    progress_dialog.close()
                                safe_show_message_widget(widget, "エラー", f"処理中に予期しないエラーが発生しました: {e}", "critical")
                            QTimer.singleShot(0, handle_error)
                    
                    thread = threading.Thread(target=run_worker, daemon=True)
                    thread.start()
                
                except Exception as e:
                    logger.error(f"プログレス表示処理中にエラー: {e}")
                    safe_show_message_widget(widget, "エラー", f"処理の初期化中にエラーが発生しました: {e}", "critical")

            # プログレス表示付き処理を非同期実行
            QTimer.singleShot(0, show_fetch_progress)

        except Exception as e:
            logger.error(f"ファイル取得処理中にエラー: {e}")
            safe_show_message_widget(widget, "エラー", f"予期しないエラーが発生しました: {e}", "critical")

    fetch_files_btn.clicked.connect(on_fetch_files)

    return widget
