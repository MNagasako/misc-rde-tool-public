"""
データセット データエントリー専用ウィジェット（最小版）
※修正タブの構造を参考にした安全な実装
Bearer Token統一管理システム対応
"""
import os
import json
import datetime
import time
import logging
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QMessageBox, QComboBox, 
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QCheckBox, QRadioButton, QProgressDialog, QApplication,
    QLineEdit, QButtonGroup
)
from qt_compat.core import Qt, QTimer, QUrl
from qt_compat.gui import QDesktopServices
from config.common import get_dynamic_file_path
from core.bearer_token_manager import BearerTokenManager
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

# ロガー設定
logger = logging.getLogger(__name__)


def create_dataset_dataentry_widget(parent, title, create_auto_resize_button):
    """データセット データエントリー専用ウィジェット（最小版）"""
    widget = QWidget()
    layout = QVBoxLayout()
    
    # フィルタ設定エリア（修正タブと同じ構成）
    filter_widget = QWidget()
    filter_layout = QVBoxLayout()
    filter_layout.setContentsMargins(0, 0, 0, 0)
    
    # フィルタタイプ選択（ラジオボタン）
    filter_type_widget = QWidget()
    filter_type_layout = QHBoxLayout()
    filter_type_layout.setContentsMargins(0, 0, 0, 0)
    
    filter_type_label = QLabel("表示データセット:")
    filter_type_label.setMinimumWidth(120)
    filter_type_label.setStyleSheet("font-weight: bold;")
    
    filter_user_only_radio = QRadioButton("ユーザー所属のみ")
    filter_others_only_radio = QRadioButton("その他のみ")
    filter_all_radio = QRadioButton("すべて")
    filter_user_only_radio.setChecked(True)  # デフォルトは「ユーザー所属のみ」
    
    filter_type_layout.addWidget(filter_type_label)
    filter_type_layout.addWidget(filter_user_only_radio)
    filter_type_layout.addWidget(filter_others_only_radio)
    filter_type_layout.addWidget(filter_all_radio)
    filter_type_layout.addStretch()
    
    filter_type_widget.setLayout(filter_type_layout)
    filter_layout.addWidget(filter_type_widget)
    
    # サブグループフィルタは除去（grantNumberのみでフィルタ）
    
    # グラント番号フィルタ（修正タブと同様）
    grant_filter_widget = QWidget()
    grant_filter_layout = QHBoxLayout()
    grant_filter_layout.setContentsMargins(0, 0, 0, 0)
    
    grant_filter_label = QLabel("課題番号:")
    grant_filter_label.setMinimumWidth(120)
    grant_filter_label.setStyleSheet("font-weight: bold;")
    
    grant_filter_input = QLineEdit()
    grant_filter_input.setPlaceholderText("課題番号で絞り込み（部分一致）")
    grant_filter_input.setMinimumWidth(200)
    
    grant_filter_layout.addWidget(grant_filter_label)
    grant_filter_layout.addWidget(grant_filter_input)
    grant_filter_layout.addStretch()
    
    grant_filter_widget.setLayout(grant_filter_layout)
    filter_layout.addWidget(grant_filter_widget)
    
    filter_widget.setLayout(filter_layout)
    layout.addWidget(filter_widget)
    
    # データセット選択
    dataset_selection_widget = QWidget()
    dataset_selection_layout = QHBoxLayout()
    dataset_selection_layout.setContentsMargins(0, 0, 0, 0)
    
    dataset_label = QLabel("データエントリーを表示するデータセット:")
    dataset_label.setMinimumWidth(200)
    dataset_combo = QComboBox()
    dataset_combo.setMinimumWidth(650)
    dataset_combo.setEditable(True)
    dataset_combo.setInsertPolicy(QComboBox.NoInsert)
    dataset_combo.setMaxVisibleItems(12)

    # ▼ボタン追加
    show_all_btn = QPushButton("▼")
    show_all_btn.setToolTip("全件リスト表示")
    show_all_btn.setFixedWidth(28)
    show_all_btn.clicked.connect(dataset_combo.showPopup)

    dataset_selection_layout.addWidget(dataset_label)
    dataset_selection_layout.addWidget(dataset_combo)
    dataset_selection_layout.addWidget(show_all_btn)  # ←ここを追加
    dataset_selection_widget.setLayout(dataset_selection_layout)
    layout.addWidget(dataset_selection_widget)
    
    # データエントリー取得・表示コントロール
    control_widget = QWidget()
    control_layout = QHBoxLayout()
    control_layout.setContentsMargins(0, 0, 0, 0)
    
    fetch_button = QPushButton("データエントリー取得")
    refresh_dataset_button = QPushButton("データセット一覧更新")
    info_bg = get_color(ThemeKey.BUTTON_INFO_BACKGROUND)
    info_text = get_color(ThemeKey.BUTTON_INFO_TEXT)
    info_border = get_color(ThemeKey.BUTTON_INFO_BORDER)
    info_hover = get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)
    info_pressed = get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)
    common_button_style = f"""
        QPushButton {{
            background-color: {info_bg};
            color: {info_text};
            font-weight: bold;
            border-radius: 6px;
            padding: 8px 16px;
            border: 1px solid {info_border};
        }}
        QPushButton:hover {{
            background-color: {info_hover};
        }}
        QPushButton:pressed {{
            background-color: {info_pressed};
        }}
        QPushButton:disabled {{
            background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
        }}
    """.strip()
    fetch_button.setStyleSheet(common_button_style)
    refresh_dataset_button.setStyleSheet(common_button_style)
    
    show_all_entries_button = QPushButton("全エントリー表示")
    show_all_entries_button.setStyleSheet(f"""
        background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
        color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
        font-weight: bold;
        border-radius: 6px;
        padding: 8px 16px;
    """)
    
    control_layout.addWidget(fetch_button)
                    # サブグループフィルタ除去
    
    control_widget.setLayout(control_layout)
    layout.addWidget(control_widget)
    
    # 強制更新チェックボックス
    force_refresh_checkbox = QCheckBox("強制更新（既存のキャッシュを無視）")
    force_refresh_checkbox.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_WARNING)}; font-weight: bold;")
    layout.addWidget(force_refresh_checkbox)
    fetch_button.setMaximumWidth(150)
    fetch_button.setStyleSheet(f"""
        background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
        color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
        font-weight: bold;
        border-radius: 4px;
        padding: 8px;
    """)
    
    force_refresh_checkbox = QCheckBox("強制更新")
    force_refresh_checkbox.setToolTip("既存のJSONファイルが5分以内でも強制的に再取得します")
    
    control_layout.addWidget(fetch_button)
    control_layout.addWidget(force_refresh_checkbox)
    control_layout.addStretch()
    
    control_widget.setLayout(control_layout)
    layout.addWidget(control_widget)
    
    # データエントリー情報表示エリア
    info_group = QGroupBox("データエントリー情報")
    info_layout = QVBoxLayout()
    
    # 基本情報表示
    basic_info_widget = QWidget()
    basic_info_layout = QVBoxLayout()
    basic_info_layout.setContentsMargins(0, 0, 0, 0)
    
    dataset_info_label = QLabel("データセット: 未選択")
    dataset_info_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)}; margin: 5px;")
    
    entry_count_label = QLabel("データエントリー件数: -")
    entry_count_label.setStyleSheet(f"font-size: 12px; color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 5px;")
    
    last_updated_label = QLabel("最終取得: -")
    last_updated_label.setStyleSheet(f"font-size: 12px; color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 5px;")
    
    basic_info_layout.addWidget(dataset_info_label)
    basic_info_layout.addWidget(entry_count_label)
    basic_info_layout.addWidget(last_updated_label)
    
    basic_info_widget.setLayout(basic_info_layout)
    info_layout.addWidget(basic_info_widget)
    
    # データエントリー一覧テーブル
    # --- fileTypeごとのカラム拡張 ---
    from classes.data_fetch2.conf.file_filter_config import FILE_TYPES
    # ファイルタイプごとの短い日本語ラベル
    FILE_TYPE_LABELS = {
        "MAIN_IMAGE": "MAIN",
        "STRUCTURED": "STRCT",
        "NONSHARED_RAW": "NOSHARE",
        "RAW": "RAW",
        "META": "META",
        "ATTACHEMENT": "ATTACH",
        "THUMBNAIL": "THUMB",
        "OTHER": "OTHER"
    }
    base_headers = ["No", "名前", "説明", "ファイル", "画像", "作成日"]
    filetype_headers = [f"{FILE_TYPE_LABELS.get(ft, ft)}" for ft in FILE_TYPES]
    all_headers = base_headers + filetype_headers + ["ブラウザ"]
    entry_table = QTableWidget()
    entry_table.setColumnCount(len(all_headers))
    entry_table.setHorizontalHeaderLabels(all_headers)
    # テーブルの設定
    header = entry_table.horizontalHeader()
    # 各列の幅を内容に応じて自動調整（可変）
    for col in range(len(all_headers)):
        header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
    header.setStretchLastSection(False)
    entry_table.setAlternatingRowColors(True)
    entry_table.setSelectionBehavior(QTableWidget.SelectRows)
    entry_table.setSortingEnabled(True)
    entry_table.setMinimumHeight(300)
    # 列ヘッダの折り返し表示（word-wrap）
    entry_table.horizontalHeader().setDefaultAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
    entry_table.setWordWrap(True)
    # ヘッダのスタイルで折り返しを強制
    entry_table.setStyleSheet("QHeaderView::section { padding: 4px; white-space: normal; }")
    
    info_layout.addWidget(entry_table)
    info_group.setLayout(info_layout)
    layout.addWidget(info_group)
    
    # データセットキャッシュシステム（最小版）
    dataset_cache = {
        "raw_data": None,
        "last_modified": None,
        "user_grant_numbers": None,
        "filtered_datasets": {},
        "display_data": {}
    }
    
    def load_subgroups():
        """サブグループ情報を読み込んでコンボボックスに設定"""
        try:
            # サブグループフィルタ除去
            
            # subGroup.jsonから読み込み
            subgroup_path = get_dynamic_file_path("output/rde/data/subGroup.json")
            if os.path.exists(subgroup_path):
                with open(subgroup_path, 'r', encoding='utf-8') as f:
                    subgroup_data = json.load(f)
                
                # 正しいデータ構造から読み込み: {"data": {...}, "included": [...]}
                subgroups = subgroup_data.get("included", [])
                
                for subgroup in subgroups:
                    # データ構造の検証
                    if not isinstance(subgroup, dict):
                        logger.warning("サブグループデータが辞書でない - スキップ")
                        continue
                    
                    attrs = subgroup.get("attributes", {})
                    if not isinstance(attrs, dict):
                        logger.warning("サブグループのattributesが辞書でない - スキップ")
                        continue
                    
                    subgroup_id = subgroup.get("id", "")
                    subgroup_name = attrs.get("name", "")
                    display_text = f"{subgroup_name} ({subgroup_id})"
                    # サブグループフィルタ除去
            
            # サブグループフィルタ除去
            
        except Exception as e:
            logger.error("サブグループ読み込みエラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def get_user_grant_numbers():
        """
        ログインユーザーが属するサブグループのgrantNumberリストを取得
        修正タブと同様の処理
        """
        sub_group_path = get_dynamic_file_path('output/rde/data/subGroup.json')
        self_path = get_dynamic_file_path('output/rde/data/self.json')
        user_grant_numbers = set()
        
        logger.debug("サブグループファイルパス: %s", sub_group_path)
        logger.debug("セルフファイルパス: %s", self_path)
        logger.debug("サブグループファイル存在: %s", os.path.exists(sub_group_path))
        logger.debug("セルフファイル存在: %s", os.path.exists(self_path))
        
        try:
            # ログインユーザーID取得
            with open(self_path, encoding="utf-8") as f:
                self_data = json.load(f)
            user_id = self_data.get("data", {}).get("id", None)
            logger.debug("ユーザーID: %s", user_id)
            
            if not user_id:
                logger.error("self.jsonからユーザーIDが取得できませんでした。")
                return user_grant_numbers
            
            # ユーザーが属するサブグループを抽出
            with open(sub_group_path, encoding="utf-8") as f:
                sub_group_data = json.load(f)
            
            groups_count = 0
            for item in sub_group_data.get("included", []):
                if item.get("type") == "group" and item.get("attributes", {}).get("groupType") == "TEAM":
                    groups_count += 1
                    roles = item.get("attributes", {}).get("roles", [])
                    # ユーザーがこのグループのメンバーかチェック
                    user_in_group = False
                    for r in roles:
                        if r.get("userId") == user_id:
                            user_in_group = True
                            break
                    
                    if user_in_group:
                        # このグループのgrantNumbersを取得
                        subjects = item.get("attributes", {}).get("subjects", [])
                        group_name = item.get("attributes", {}).get("name", "不明")
                        logger.debug("ユーザーが所属するグループ: '%s' (課題数: %s)", group_name, len(subjects))
                        
                        for subject in subjects:
                            grant_number = subject.get("grantNumber", "")
                            if grant_number:
                                user_grant_numbers.add(grant_number)
                                logger.debug("課題番号追加: %s", grant_number)
            
            logger.debug("検査したTEAMグループ数: %s", groups_count)
            logger.debug("最終的なユーザー課題番号: %s", sorted(user_grant_numbers))
        
        except Exception as e:
            logger.error("ユーザーgrantNumber取得に失敗: %s", e)
            import traceback
            traceback.print_exc()
        
        return user_grant_numbers

    def populate_dataset_combo_with_filter():
        """フィルタリングを適用してデータセットコンボボックスを更新"""
        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        
        if not os.path.exists(dataset_path):
            dataset_combo.clear()
            dataset_combo.addItem("-- データセット情報がありません --", "")
            QMessageBox.warning(widget, "注意", "データセット情報が見つかりません。\n基本情報取得を実行してください。")
            return
        
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            datasets = data.get('data', []) if isinstance(data, dict) else data
            
            # フィルタリング適用
            filtered_datasets = []
            
            # ユーザー所属・その他・すべてのフィルタ
            filter_type = "user_only"
            if filter_others_only_radio.isChecked():
                filter_type = "others_only"
            elif filter_all_radio.isChecked():
                filter_type = "all"
            
            # サブグループフィルタ
            # サブグループフィルタ除去
            
            # ユーザーのgrantNumber一覧を取得
            user_grant_numbers = get_user_grant_numbers()
            
            # グラント番号フィルタ
            grant_filter_text = grant_filter_input.text().strip().lower()
            
            # フィルタリング処理
            filtered_datasets = []
            user_datasets = []
            other_datasets = []
            
            for dataset in datasets:
                attrs = dataset.get("attributes", {})
                dataset_id = dataset.get("id", "")
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                
                # グラント番号フィルタを先に適用
                if grant_filter_text and grant_filter_text not in grant_number.lower():
                    continue
                
                # ユーザー所属かどうかで分類
                if grant_number in user_grant_numbers:
                    user_datasets.append(dataset)
                else:
                    other_datasets.append(dataset)
            
            # フィルタタイプに基づいて表示対象を決定
            if filter_type == "user_only":
                filtered_datasets = user_datasets
                logger.debug("フィルタ適用: ユーザー所属のみ (%s件)", len(filtered_datasets))
            elif filter_type == "others_only":
                filtered_datasets = other_datasets
                logger.debug("フィルタ適用: その他のみ (%s件)", len(filtered_datasets))
            elif filter_type == "all":
                filtered_datasets = user_datasets + other_datasets
                logger.debug("フィルタ適用: すべて (ユーザー所属: %s件, その他: %s件, 合計: %s件)", len(user_datasets), len(other_datasets), len(filtered_datasets))
            
            # コンボボックス更新
            dataset_combo.blockSignals(True)
            dataset_combo.clear()
            dataset_combo.addItem("-- データセットを選択 --", "")
            
            for dataset in filtered_datasets:
                attrs = dataset.get("attributes", {})
                dataset_id = dataset.get("id", "")
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                dataset_type = attrs.get("datasetType", "")
                
                # ユーザー所属かどうかで表示を区別
                if grant_number in user_grant_numbers:
                    display_text = f"★ {grant_number} - {name} (ID: {dataset_id})"
                else:
                    display_text = f"{grant_number} - {name} (ID: {dataset_id})"
                
                if dataset_type:
                    display_text += f" [{dataset_type}]"
                
                dataset_combo.addItem(display_text, dataset_id)
            
            dataset_combo.blockSignals(False)
            
            logger.info("フィルタ適用後のデータセット: %s件 (全%s件中)", len(filtered_datasets), len(datasets))
            
        except Exception as e:
            logger.error("dataset.json読み込みエラー: %s", e)
            dataset_combo.clear()
            dataset_combo.addItem("-- データセット読み込みエラー --", "")
    
    def get_selected_dataset_id():
        """選択されたデータセットのIDを取得"""
        return dataset_combo.currentData()
    
    def update_dataentry_display(dataset_id=None, force_refresh=False):
        """データエントリー情報の表示を更新"""
        if not dataset_id:
            dataset_id = get_selected_dataset_id()
        
        if not dataset_id:
            dataset_info_label.setText("データセット: 未選択")
            entry_count_label.setText("データエントリー件数: -")
            last_updated_label.setText("最終取得: -")
            entry_table.setRowCount(0)
            return
        
        # JSONファイルの存在確認と更新チェック
        dataentry_file = get_dynamic_file_path(f"output/rde/data/dataEntry/{dataset_id}.json")
        
        needs_fetch = True
        if os.path.exists(dataentry_file) and not force_refresh:
            # ファイルの更新時刻をチェック（5分以内なら取得スキップ）
            file_mtime = os.path.getmtime(dataentry_file)
            current_time = time.time()
            
            if current_time - file_mtime < 300:  # 5分 = 300秒
                needs_fetch = False
            logger.debug("[データエントリーキャッシュ] needs_fetch=%s now=%s file=%s 最終更新: %s", needs_fetch, current_time, dataentry_file, datetime.datetime.fromtimestamp(file_mtime))
        if needs_fetch:
            # データエントリー情報を取得する必要がある
            dataset_info_label.setText(f"データセット: {dataset_id} (取得中...)")
            entry_count_label.setText("データエントリー件数: 取得中...")
            last_updated_label.setText("最終取得: 取得中...")
            entry_table.setRowCount(0)
            logger.debug("[データエントリー取得] fetch_dataentry_info(%s, %s)", dataset_id, force_refresh)
                # 少し遅延させてから取得処理を実行
            QTimer.singleShot(100, lambda: fetch_dataentry_info(dataset_id, force_refresh))
        else:
            # 既存のJSONファイルを読み込んで表示
            load_and_display_dataentry_info(dataset_id)
    
    def fetch_dataentry_info(dataset_id, force_refresh=False):
        """データエントリー情報をAPIから取得"""
        
        try:
            # プログレスダイアログを表示
            progress = QProgressDialog("データエントリー情報を取得中...", "キャンセル", 0, 100, widget)
            progress.setWindowModality(Qt.WindowModal)
            progress.setAutoClose(True)
            progress.setValue(10)
            QApplication.processEvents()
            
            # Bearer Token統一管理システムで取得
            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
            if not bearer_token:
                QMessageBox.warning(widget, "認証エラー", "Bearer Tokenが取得できません。ログインを確認してください。")
                return
            
            progress.setValue(30)
            QApplication.processEvents()
            
            # データエントリー取得API呼び出し（実際のAPI呼び出しコードに置き換える）
            # ここから先を修正。basic モジュールとかのデータエントリー取得機能を使うといいと思う。
            
            from classes.dataset.core.dataset_dataentry_logic import fetch_dataset_dataentry
            
            progress.setValue(50)
            QApplication.processEvents()
            
            success = fetch_dataset_dataentry(dataset_id, bearer_token, force_refresh)
            #return #debug 一時的
            progress.setValue(90)
            QApplication.processEvents()
            logger.debug("fetch_dataset_dataentry result: %s", success)
            if success:
                # 取得成功、表示を更新
                load_and_display_dataentry_info(dataset_id)
                progress.setValue(100)
                QTimer.singleShot(100, progress.close)
            else:
                progress.close()
                QMessageBox.warning(widget, "取得エラー", "データエントリー情報の取得に失敗しました。")
            
        except ImportError:
            logger.warning("データエントリーロジックモジュールが見つかりません。ダミーデータで対応します。")
            # データエントリーロジックモジュールが見つからない場合、ダミーデータで対応
            progress.close()
            # QMessageBox.information(widget, "開発中", "データエントリー取得機能は開発中です。\n既存のJSONファイルがあれば表示されます。")
            load_and_display_dataentry_info(dataset_id)
            
        except Exception as e:
            logger.error("データエントリー取得エラー: %s", e)
            if progress:
                progress.close()
            logger.error("データエントリー取得エラー: %s", e)
            dataset_info_label.setText(f"データセット: {dataset_id} (取得エラー)")
            entry_count_label.setText("データエントリー件数: エラー")
            last_updated_label.setText("最終取得: エラー")
            # 基本情報取得機能を使用してデータエントリー情報を取得
            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
            if not bearer_token:
                QMessageBox.warning(widget, "エラー", "Bearer Tokenが取得できません。ログインを確認してください。")
                return
            
            # 既存の fetch_data_entry_info_from_api を使用
            from classes.basic.core.basic_info_logic import fetch_data_entry_info_from_api
            
            output_dir = get_dynamic_file_path("output/rde/data/dataEntry")
            
            # 強制更新の場合は既存ファイルを削除
            if force_refresh:
                dataentry_file = os.path.join(output_dir, f"{dataset_id}.json")
                if os.path.exists(dataentry_file):
                    os.remove(dataentry_file)
                    logger.info("強制更新のため既存ファイルを削除: %s", dataentry_file)
            
            # データエントリー情報を取得
            fetch_data_entry_info_from_api(bearer_token, dataset_id, output_dir)
            
            # 取得完了後、表示を更新
            QTimer.singleShot(500, lambda: load_and_display_dataentry_info(dataset_id))
            
        except Exception as e:
            logger.error("データエントリー取得エラー: %s", e)
            QMessageBox.critical(widget, "エラー", f"データエントリー情報の取得に失敗しました:\n{e}")
            dataset_info_label.setText(f"データセット: {dataset_id} (取得エラー)")
            entry_count_label.setText("データエントリー件数: エラー")
            last_updated_label.setText("最終取得: エラー")
    
    def load_and_display_dataentry_info(dataset_id):
        """JSONファイルからデータエントリー情報を読み込んで表示"""
        try:
            dataentry_file = get_dynamic_file_path(f"output/rde/data/dataEntry/{dataset_id}.json")
            
            if not os.path.exists(dataentry_file):
                dataset_info_label.setText(f"データセット: {dataset_id} (データなし)")
                entry_count_label.setText("データエントリー件数: 0")
                last_updated_label.setText("最終取得: なし")
                entry_table.setRowCount(0)
                return
            
            # JSONファイルを読み込み
            with open(dataentry_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 基本情報を更新
            entry_count = len(data.get('data', []))
            file_mtime = os.path.getmtime(dataentry_file)
            last_updated = datetime.datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            dataset_info_label.setText(f"データセット: {dataset_id}")
            entry_count_label.setText(f"データエントリー件数: {entry_count}件")
            last_updated_label.setText(f"最終取得: {last_updated} path: {dataentry_file}")
            
            # テーブルにデータを設定
            entry_table.setRowCount(entry_count)
            from classes.data_fetch2.conf.file_filter_config import FILE_TYPES
            base_col_count = 6  # データ番号, 名前, 説明, ファイル数, 画像ファイル数, 作成日
            for row, entry in enumerate(data.get('data', [])):
                attributes = entry.get('attributes', {})
                data_number = str(attributes.get('dataNumber', ''))
                entry_table.setItem(row, 0, QTableWidgetItem(data_number))
                name = attributes.get('name', '')
                entry_table.setItem(row, 1, QTableWidgetItem(name))
                description = attributes.get('description', '')
                entry_table.setItem(row, 2, QTableWidgetItem(description))
                num_files = str(attributes.get('numberOfFiles', 0))
                entry_table.setItem(row, 3, QTableWidgetItem(num_files))
                num_image_files = str(attributes.get('numberOfImageFiles', 0))
                entry_table.setItem(row, 4, QTableWidgetItem(num_image_files))
                # 作成日: 'createdAt' または 'created' を参照
                created_at = attributes.get('createdAt') or attributes.get('created') or ''
                if created_at:
                    try:
                        dt = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        formatted_date = dt.strftime('%Y-%m-%d')
                    except Exception:
                        formatted_date = created_at
                else:
                    formatted_date = '--'
                entry_table.setItem(row, 5, QTableWidgetItem(formatted_date))
                # --- fileTypeごとのファイル数集計 ---
                included = data.get('included', [])
                entry_id = entry.get('id', '')
                # entryのrelationships.files.dataからファイルIDリストを取得
                file_ids = set()
                rel_files = entry.get('relationships', {}).get('files', {}).get('data', [])
                for fobj in rel_files:
                    if isinstance(fobj, dict) and fobj.get('type') == 'file' and fobj.get('id'):
                        file_ids.add(fobj['id'])
                # included配列からidがfile_idsに含まれるfile要素を抽出
                files_for_entry = [f for f in included if f.get('type') == 'file' and f.get('id') in file_ids]
                # デバッグ出力
                #print(f"[DEBUG] entry_id={entry_id} name={name} data_number={data_number} file_ids={list(file_ids)}")
                #print(f"  [DEBUG] files_for_entry count={len(files_for_entry)} ids={[f.get('id') for f in files_for_entry]}")
                filetype_counts = {ft: 0 for ft in FILE_TYPES}
                for f in files_for_entry:
                    ft = f.get('attributes', {}).get('fileType')
                    # print(f"    [DEBUG] file id={f.get('id')} fileType={ft}")
                    if ft in filetype_counts:
                        filetype_counts[ft] += 1
                #print(f"  [DEBUG] filetype_counts={filetype_counts}")
                # fileTypeカウント列はすべてsetItemで数値のみ（ボタン禁止）
                for i, ft in enumerate(FILE_TYPES):
                    item = QTableWidgetItem(str(filetype_counts[ft]))
                    entry_table.setItem(row, base_col_count + i, item)
                # 「ブラウザ」列のみ setCellWidget でボタン
                browser_col = base_col_count + len(FILE_TYPES)
                link_button = QPushButton("開く")
                link_button.setStyleSheet(f"""
                    background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                    font-size: 10px;
                    padding: 2px 6px;
                    border-radius: 3px;
                """)
                def create_link_handler(entry_id):
                    def on_link_click():
                        url = f"https://rde.nims.go.jp/rde/datasets/data/{entry_id}"
                        QDesktopServices.openUrl(QUrl(url))
                    return on_link_click
                link_button.clicked.connect(create_link_handler(entry_id))
                entry_table.setCellWidget(row, browser_col, link_button)
                
                # 説明
                description = attributes.get('description', '')
                entry_table.setItem(row, 2, QTableWidgetItem(description))
                
                # ファイル数
                num_files = str(attributes.get('numberOfFiles', 0))
                entry_table.setItem(row, 3, QTableWidgetItem(num_files))
                
                # 画像ファイル数
                num_image_files = str(attributes.get('numberOfImageFiles', 0))
                entry_table.setItem(row, 4, QTableWidgetItem(num_image_files))
                
           
        except Exception as e:
            logger.error("データエントリー情報表示エラー: %s", e)
            dataset_info_label.setText(f"データセット: {dataset_id} (表示エラー)")
            entry_count_label.setText("データエントリー件数: エラー")
            last_updated_label.setText("最終取得: エラー")
            
        except Exception as e:
            logger.error("データエントリー表示エラー: %s", e)
            QMessageBox.critical(widget, "エラー", f"データエントリー情報の表示に失敗しました:\n{e}")
            dataset_info_label.setText(f"データセット: {dataset_id} (表示エラー)")
            entry_count_label.setText("データエントリー件数: エラー")
            last_updated_label.setText("最終取得: エラー")
    
    # イベントハンドラー設定
    def on_dataset_selection_changed():
        """データセット選択変更時の処理"""
        dataset_id = get_selected_dataset_id()
        if dataset_id:
            update_dataentry_display(dataset_id, False)
    
    def on_fetch_button_clicked():
        """取得ボタンクリック時の処理"""
        dataset_id = get_selected_dataset_id()
        if not dataset_id:
            QMessageBox.warning(widget, "警告", "データセットを選択してください。")
            return
        
        force_refresh = force_refresh_checkbox.isChecked()
        update_dataentry_display(dataset_id, force_refresh)
    
    def show_all_entries():
        """全データエントリーを表示"""
        try:
            dataentry_dir = get_dynamic_file_path("output/rde/data/dataEntry")
            if not os.path.exists(dataentry_dir):
                QMessageBox.warning(widget, "警告", "データエントリーディレクトリが見つかりません。")
                return
            
            # すべてのデータエントリーJSONファイルを読み込み
            all_entries = []
            json_files = [f for f in os.listdir(dataentry_dir) if f.endswith('.json')]
            
            for json_file in json_files:
                dataset_id = json_file[:-5]  # .jsonを除去
                filepath = os.path.join(dataentry_dir, json_file)
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    for entry in data.get('data', []):
                        entry['dataset_id'] = dataset_id  # データセットID情報を追加
                        all_entries.append(entry)
                        
                except Exception as e:
                    logger.error("%s 読み込みエラー: %s", json_file, e)
            
            # テーブル表示を更新
            dataset_info_label.setText("データセット: 全エントリー表示")
            entry_count_label.setText(f"データエントリー件数: {len(all_entries)}件")
            last_updated_label.setText("最終取得: 全ファイル統合")
            
            entry_table.setRowCount(len(all_entries))
            
            from classes.data_fetch2.conf.file_filter_config import FILE_TYPES
            FILE_TYPE_LABELS = {
                "MAIN_IMAGE": "MAIN",
                "STRUCTURED": "STRCT",
                "NONSHARED_RAW": "NOSHARE",
                "RAW": "RAW",
                "META": "META",
                "ATTACHEMENT": "ATTACH",
                "THUMBNAIL": "THUMB",
                "OTHER": "OTHER"
            }
            base_col_count = 6
            for row, entry in enumerate(all_entries):
                attributes = entry.get('attributes', {})
                data_number = f"{entry.get('dataset_id', '')}-{attributes.get('dataNumber', '')}"
                entry_table.setItem(row, 0, QTableWidgetItem(data_number))
                name = attributes.get('name', '')
                entry_table.setItem(row, 1, QTableWidgetItem(name))
                description = attributes.get('description', '')
                entry_table.setItem(row, 2, QTableWidgetItem(description))
                num_files = str(attributes.get('numberOfFiles', 0))
                entry_table.setItem(row, 3, QTableWidgetItem(num_files))
                num_image_files = str(attributes.get('numberOfImageFiles', 0))
                entry_table.setItem(row, 4, QTableWidgetItem(num_image_files))
                # 作成日: 'createdAt' または 'created' を参照
                created_at = attributes.get('createdAt') or attributes.get('created') or ''
                if created_at:
                    try:
                        dt = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        formatted_date = dt.strftime('%Y-%m-%d')
                    except Exception:
                        formatted_date = created_at
                else:
                    formatted_date = '----'
                entry_table.setItem(row, 5, QTableWidgetItem(formatted_date))

                # --- fileTypeごとのファイル数集計 ---
                included = entry.get('included', []) if 'included' in entry else []
                entry_id = entry.get('id', '')
                file_ids = set()
                rel_files = entry.get('relationships', {}).get('files', {}).get('data', [])
                for fobj in rel_files:
                    if isinstance(fobj, dict) and fobj.get('type') == 'file' and fobj.get('id'):
                        file_ids.add(fobj['id'])
                files_for_entry = [f for f in included if f.get('type') == 'file' and f.get('id') in file_ids]
                filetype_counts = {ft: 0 for ft in FILE_TYPES}
                for f in files_for_entry:
                    ft = f.get('attributes', {}).get('fileType')
                    if ft in filetype_counts:
                        filetype_counts[ft] += 1
                # fileTypeカウント列はすべてsetItemで数値のみ（ボタン禁止）
                for i, ft in enumerate(FILE_TYPES):
                    item = QTableWidgetItem(str(filetype_counts[ft]))
                    entry_table.setItem(row, base_col_count + i, item)
                # 「ブラウザ」列のみ setCellWidget でボタン
                browser_col = base_col_count + len(FILE_TYPES)
                link_button = QPushButton("開く")
                link_button.setStyleSheet(f"""
                    background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                    font-size: 10px;
                    padding: 2px 6px;
                    border-radius: 3px;
                """)
                entry_id = entry.get('id', '')
                def create_link_handler(entry_id):
                    def on_link_click():
                        url = f"https://rde.nims.go.jp/rde/datasets/data/{entry_id}"
                        QDesktopServices.openUrl(QUrl(url))
                    return on_link_click
                link_button.clicked.connect(create_link_handler(entry_id))
                entry_table.setCellWidget(row, browser_col, link_button)
            
        except Exception as e:
            QMessageBox.critical(widget, "エラー", f"全エントリー表示中にエラーが発生しました:\n{e}")
    
    # イベントハンドラー
    def on_dataset_selection_changed():
        """データセット選択変更時のハンドラー"""
        update_dataentry_display()
    
    def on_fetch_button_clicked():
        """データエントリー取得ボタンクリック時のハンドラー"""
        dataset_id = get_selected_dataset_id()
        if not dataset_id:
            QMessageBox.warning(widget, "警告", "データセットを選択してください。")
            return
        
        force_refresh = force_refresh_checkbox.isChecked()
        update_dataentry_display(dataset_id, force_refresh)
    
    def on_refresh_dataset_clicked():
        """データセット一覧更新ボタンクリック時のハンドラー"""
        load_subgroups()
        populate_dataset_combo_with_filter()
    
    def on_filter_changed():
        """フィルタ変更時のハンドラー"""
        populate_dataset_combo_with_filter()
    
    # イベント接続
    dataset_combo.currentTextChanged.connect(on_dataset_selection_changed)
    fetch_button.clicked.connect(on_fetch_button_clicked)
    refresh_dataset_button.clicked.connect(on_refresh_dataset_clicked)
    show_all_entries_button.clicked.connect(show_all_entries)
    
    # フィルタ変更時のイベント接続
    filter_user_only_radio.toggled.connect(on_filter_changed)
    filter_others_only_radio.toggled.connect(on_filter_changed)
    filter_all_radio.toggled.connect(on_filter_changed)
    # サブグループフィルタ除去
    grant_filter_input.textChanged.connect(on_filter_changed)
    
    # 初期データ読み込み
    QTimer.singleShot(100, load_subgroups)
    QTimer.singleShot(200, populate_dataset_combo_with_filter)
    
    widget.setLayout(layout)
    return widget

from qt_compat.widgets import QWidget, QHBoxLayout, QComboBox, QPushButton, QLabel

class DatasetDataEntryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # ラベル
        label = QLabel("データエントリーを表示するデータセット:")
        layout.addWidget(label)

        # 横並びウィジェット
        h_widget = QWidget()
        h_layout = QHBoxLayout(h_widget)
        h_layout.setContentsMargins(0, 0, 0, 0)

        # コンボボックス
        self.dataset_combo = QComboBox()
        h_layout.addWidget(self.dataset_combo)

        # リスト表示ボタン
        self.show_all_btn = QPushButton("▼")
        self.show_all_btn.setToolTip("全件リスト表示")
        self.show_all_btn.setFixedWidth(28)
        h_layout.addWidget(self.show_all_btn)

        # 横並びウィジェットをレイアウトに追加
        layout.addWidget(h_widget)

        # ボタン押下時にドロップダウンを開く
        self.show_all_btn.clicked.connect(self.dataset_combo.showPopup)