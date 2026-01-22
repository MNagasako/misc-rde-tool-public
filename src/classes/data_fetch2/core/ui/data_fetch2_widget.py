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
from qt_compat.widgets import QVBoxLayout, QLabel, QWidget, QMessageBox, QProgressDialog, QComboBox, QPushButton, QHBoxLayout
from qt_compat.core import QTimer, Qt, QMetaObject, Q_ARG, QUrl, Signal, QObject
from qt_compat.gui import QDesktopServices
from config.common import OUTPUT_DIR, DATAFILES_DIR, get_dynamic_file_path
from classes.theme import ThemeKey
from classes.theme.theme_manager import get_color
from classes.utils.label_style import apply_label_style
from classes.utils.dataset_launch_manager import DatasetLaunchManager, DatasetPayload

# ロガー設定
# シグナル用ヘルパークラス
class SummaryUpdateSignal(QObject):
    """内訳ラベル更新用シグナル"""
    update_text = Signal(str)

_summary_signal = SummaryUpdateSignal()

logger = logging.getLogger(__name__)
if not logger.handlers:
    _h = logging.StreamHandler()
    _fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


def relax_fetch2_filters_for_launch(dropdown_widget) -> bool:
    """Reset filters to the broadest state before applying dataset handoff."""
    if dropdown_widget is None:
        return False

    reset_fn = getattr(dropdown_widget, 'reset_filters', None)
    reload_fn = getattr(dropdown_widget, 'reload_datasets', None)
    changed = False

    try:
        if callable(reset_fn):
            try:
                changed = bool(reset_fn(reload=False))
            except TypeError:
                reset_fn()
                changed = True
    except Exception:  # pragma: no cover - defensive logging
        logger.debug("data_fetch2: reset_filters failed", exc_info=True)

    try:
        if callable(reload_fn):
            reload_fn()
        else:
            changed = False
    except Exception:  # pragma: no cover - defensive logging
        logger.debug("data_fetch2: reload_datasets failed", exc_info=True)

    return changed


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
    from qt_compat.core import Qt, QObject, QEvent
    from qt_compat import QtGui
    import time
    
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
    apply_label_style(share_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    
    # ラジオボタン共通スタイル（視認性向上）
    radio_style = f"""
        QRadioButton {{
            spacing: 5px;
            color: {get_color(ThemeKey.TEXT_PRIMARY)};
            font-size: 10pt;
        }}
        QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
            border-radius: 10px;
            background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
        }}
        QRadioButton::indicator:hover {{
            border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
            background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};
        }}
        QRadioButton::indicator:checked {{
            background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
            border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
        }}
    """
    
    share_both_radio = QRadioButton("両方")
    share_both_radio.setStyleSheet(radio_style)
    share_enabled_radio = QRadioButton("有効のみ")
    share_enabled_radio.setStyleSheet(radio_style)
    share_disabled_radio = QRadioButton("無効のみ")
    share_disabled_radio.setStyleSheet(radio_style)
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
    apply_label_style(member_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    
    member_both_radio = QRadioButton("両方")
    member_both_radio.setStyleSheet(radio_style)
    member_only_radio = QRadioButton("メンバーのみ")
    member_only_radio.setStyleSheet(radio_style)
    member_non_radio = QRadioButton("非メンバーのみ")
    member_non_radio.setStyleSheet(radio_style)
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
    apply_label_style(type_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    
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
    apply_label_style(grant_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    
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
    apply_label_style(count_label, get_color(ThemeKey.TEXT_MUTED), bold=True, point_size=10)
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
    
    def _build_combo_style() -> str:
        return f"""
        QComboBox {{
            background-color: {get_color(ThemeKey.COMBO_BACKGROUND)};
            color: {get_color(ThemeKey.TEXT_PRIMARY)};
            border: 1px solid {get_color(ThemeKey.COMBO_BORDER)};
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 10pt;
            min-height: 30px;
            padding-right: 35px;
        }}
        QComboBox:focus {{
            border: 1px solid {get_color(ThemeKey.COMBO_BORDER_FOCUS)};
            background-color: {get_color(ThemeKey.COMBO_BACKGROUND_FOCUS)};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 30px;
            border-left: 1px solid {get_color(ThemeKey.COMBO_BORDER_FOCUS)};
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
        }}
        QComboBox::drop-down:hover {{
            background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
        }}
        QComboBox::down-arrow {{
            width: 0;
            height: 0;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 8px solid {get_color(ThemeKey.TEXT_PRIMARY)};
            margin: 0px;
        }}
        QComboBox::down-arrow:on {{
            border-top: 8px solid {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
        }}
        QComboBox:disabled {{
            background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)};
            border: 1px solid {get_color(ThemeKey.INPUT_BORDER_DISABLED)};
        }}
    """

    # コンボボックス作成
    combo = QComboBox()
    combo.setMinimumWidth(650)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setMaxVisibleItems(15)
    # プレースホルダは項目ではなく、入力欄のヒントとして表示
    combo.lineEdit().setPlaceholderText("— データセットを選択してください —")
    
    # コンボボックス個別スタイル（フォント表示問題対策）
    # テキストが隠れないよう十分な高さとパディングを確保
    # フォーカス可視化強化（枠色+薄い背景）
    combo.setStyleSheet(_build_combo_style())
    
    # 全件表示ボタン（コンボボックスの隣に配置）
    combo_container = QWidget()
    combo_layout = QHBoxLayout()
    combo_layout.setContentsMargins(0, 0, 0, 0)
    
    show_all_btn = QPushButton("全件表示")
    #show_all_btn.setMaximumWidth(80)
    
    combo_layout.addWidget(combo)
    #combo_layout.addWidget(show_all_btn)
    combo_container.setLayout(combo_layout)
    
    layout.addWidget(combo_container)

    # 選択中データセットの日時（JST）+ サブグループ名を表示
    try:
        from classes.utils.dataset_datetime_display import create_dataset_dates_label, attach_dataset_dates_label_with_subgroup

        dataset_dates_label = create_dataset_dates_label(container)
        attach_dataset_dates_label_with_subgroup(combo=combo, label=dataset_dates_label)
        layout.addWidget(dataset_dates_label)
        container.dataset_dates_label = dataset_dates_label
    except Exception:
        container.dataset_dates_label = None
    
    def load_and_filter_datasets():
        """フィルタリング設定を適用してコンボボックスを更新"""
        try:
            t0 = time.perf_counter()
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
            
            t_read0 = time.perf_counter()
            with open(dataset_json_path, 'r', encoding='utf-8') as f:
                dataset_data = json.load(f)
            t_read1 = time.perf_counter()
            
            # データセットリストを取得（data配下かルート配下かを判定）
            if isinstance(dataset_data, dict) and 'data' in dataset_data:
                dataset_items = dataset_data['data']
            elif isinstance(dataset_data, list):
                dataset_items = dataset_data
            else:
                dataset_items = []

            # RDE側で削除済みのデータセット（404/410確認済み）は候補から除外
            try:
                from classes.utils.remote_resource_pruner import filter_out_marked_missing_ids

                dataset_items = filter_out_marked_missing_ids(
                    dataset_items or [],
                    resource_type="dataset",
                    id_key="id",
                )
            except Exception:
                # 失敗してもフィルタリング自体は継続（除外はあくまで最適化）
                pass
            
            # 現在のユーザーIDを取得
            current_user_id = get_current_user_id()
            
            # フィルタリング処理
            filtered_datasets = []
            total_count = len(dataset_items)

            t_filter0 = time.perf_counter()
            
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

            t_filter1 = time.perf_counter()
            
            # 最新フィルタ結果をキャッシュ
            try:
                container.dataset_map = {
                    dataset.get("id"): dataset
                    for dataset in filtered_datasets
                    if isinstance(dataset, dict) and dataset.get("id")
                }
            except Exception:
                container.dataset_map = {}

            # コンボボックスを更新（逐次 addItem による再描画/レイアウト更新を避け、モデルを一括差し替え）
            t_pop0 = time.perf_counter()
            combo.setUpdatesEnabled(False)
            combo.blockSignals(True)
            try:
                model = QtGui.QStandardItemModel()

                for dataset in filtered_datasets:
                    attrs = dataset.get("attributes", {})
                    dataset_id = dataset.get("id", "")
                    name = attrs.get("name", "名前なし")
                    grant_number = attrs.get("grantNumber", "")
                    dataset_type = attrs.get("datasetType", "")
                    subject_title = attrs.get("subjectTitle", "")

                    # データセットタイプの日本語表示
                    type_display = type_display_map.get(dataset_type, dataset_type) if dataset_type else ""

                    # 広域シェア状態とメンバーシップ状態（各datasetごとに評価する）
                    ds_share_enabled = check_global_sharing_enabled(dataset)
                    ds_user_member = check_user_is_member(dataset, current_user_id) if current_user_id else False
                    share_status = "🌐" if ds_share_enabled else "🔒"
                    member_status = "👤" if ds_user_member else "👥"

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

                    item = QtGui.QStandardItem(display_text)
                    item.setData(dataset_id, Qt.UserRole)
                    model.appendRow(item)

                combo.setModel(model)
                combo.setModelColumn(0)

                # QCompleter設定（モデルベースで一括）
                completer = QCompleter(model, combo)
                completer.setCompletionColumn(0)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                combo.setCompleter(completer)
            finally:
                combo.blockSignals(False)
                combo.setUpdatesEnabled(True)
            t_pop1 = time.perf_counter()
            
            # 件数表示を更新
            filtered_count = len(filtered_datasets)
            count_label.setText(f"表示中: {filtered_count}/{total_count} 件")
            
            # 何も選択されていない状態にし、プレースホルダを表示
            combo.setCurrentIndex(-1)
            # 初期状態は検索可能にする
            if combo.lineEdit():
                combo.lineEdit().setReadOnly(False)
            
            logger.info("データセットフィルタリング完了: 広域シェア=%s, メンバー=%s, タイプ=%s, 課題番号='%s', 結果=%s/%s件", share_filter_type, member_filter_type, dtype_filter, grant_filter, filtered_count, total_count)

            # 計測ログ（遅い環境の切り分け用）
            try:
                timings = {
                    'read_json_sec': round(t_read1 - t_read0, 6),
                    'filter_sec': round(t_filter1 - t_filter0, 6),
                    'populate_combo_sec': round(t_pop1 - t_pop0, 6),
                    'total_sec': round(time.perf_counter() - t0, 6),
                    'total_count': total_count,
                    'filtered_count': filtered_count,
                }
                container.dataset_dropdown_timing = timings
                logger.info("[DataFetch2] dataset_dropdown timing: %s", timings)
            except Exception:
                pass
            
        except Exception as e:
            logger.error("データセット読み込みエラー: %s", e)
            combo.clear()
            # エラー時もダミー項目は追加しない
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

    # ---- 明示的状態管理 (empty / typing / selected) ----
    container.combo_state = "empty"

    def _set_state_empty():
        combo.setCurrentIndex(-1)
        if combo.lineEdit():
            combo.lineEdit().setReadOnly(False)
            combo.lineEdit().clear()
            combo.lineEdit().setPlaceholderText("— データセットを選択してください —（部分一致検索で絞り込み可）")
        container.combo_state = "empty"

    def _set_state_selected():
        if combo.currentIndex() >= 0 and combo.lineEdit():
            combo.lineEdit().setReadOnly(True)
        container.combo_state = "selected"

    def _on_index_changed(index: int):
        if index >= 0:
            _set_state_selected()
        else:
            _set_state_empty()

    combo.currentIndexChanged.connect(_on_index_changed)

    def _on_lineedit_text_changed(text: str):
        if container.combo_state == "selected":
            return  # 読み取り専用時は無視
        if text.strip():
            container.combo_state = "typing"
        else:
            container.combo_state = "empty"
    if combo.lineEdit():
        combo.lineEdit().textChanged.connect(_on_lineedit_text_changed)

    class _ComboStateFilter(QObject):
        def eventFilter(self, watched, event):
            try:
                if watched is combo:
                    # 選択状態での単一クリックは必ず empty に戻す
                    if event.type() == QEvent.MouseButtonPress and container.combo_state == "selected":
                        _set_state_empty()
                        return False
                    # ダブルクリックはどの状態でも編集開始（empty化）
                    if event.type() == QEvent.MouseButtonDblClick:
                        _set_state_empty()
                        if combo.lineEdit():
                            combo.lineEdit().setFocus()
                        return False
                return False
            except Exception:
                return False

    combo.installEventFilter(_ComboStateFilter(combo))

    def force_reset_combo():
        _set_state_empty()
    container.force_reset_combo = force_reset_combo
    _set_state_empty()
    
    # コンテナの属性設定
    container.dataset_dropdown = combo
    container.share_button_group = share_button_group
    container.member_button_group = member_button_group
    container.type_combo = type_combo
    container.grant_edit = grant_edit
    container.search_edit = search_edit
    container.count_label = count_label
    container.dataset_map = {}
    
    # キャッシュクリアメソッドを公開
    def clear_cache():
        """
        データセットエントリーのメモリキャッシュをクリア
        グループ関連情報更新後に呼び出し、古いデータを再読み込みさせる
        """
        container.dataset_map.clear()
        logger.info("データセットエントリーキャッシュをクリアしました")
    
    container.clear_cache = clear_cache

    # テストや外部から編集モードを強制するためのユーティリティを公開
    def enable_dataset_editing():
        if combo.lineEdit():
            combo.lineEdit().setReadOnly(False)
            combo.lineEdit().setFocus()
    container.enable_dataset_editing = enable_dataset_editing
    
    # テーマ更新メソッド追加
    def refresh_theme():
        """テーマ切替時の更新処理"""
        try:
            try:
                from shiboken6 import isValid as _qt_is_valid
            except Exception:
                _qt_is_valid = None

            def _is_alive(w) -> bool:
                try:
                    if w is None:
                        return False
                    if _qt_is_valid is None:
                        return True
                    return bool(_qt_is_valid(w))
                except Exception:
                    return False

            required_widgets = [
                container,
                share_label,
                member_label,
                share_both_radio,
                share_enabled_radio,
                share_disabled_radio,
                member_both_radio,
                member_only_radio,
                member_non_radio,
                count_label,
            ]
            if not all(_is_alive(w) for w in required_widgets):
                return

            # ラベルの色更新
            apply_label_style(share_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
            apply_label_style(member_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
            
            # ラジオボタンスタイル再生成
            radio_style = f"""
                QRadioButton {{
                    spacing: 5px;
                    color: {get_color(ThemeKey.TEXT_PRIMARY)};
                    font-size: 10pt;
                }}
                QRadioButton::indicator {{
                    width: 18px;
                    height: 18px;
                    border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                    border-radius: 10px;
                    background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                }}
                QRadioButton::indicator:hover {{
                    border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};
                }}
                QRadioButton::indicator:checked {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                }}
            """
            
            # 全ラジオボタンにスタイル適用
            share_both_radio.setStyleSheet(radio_style)
            share_enabled_radio.setStyleSheet(radio_style)
            share_disabled_radio.setStyleSheet(radio_style)
            member_both_radio.setStyleSheet(radio_style)
            member_only_radio.setStyleSheet(radio_style)
            member_non_radio.setStyleSheet(radio_style)
            
            # 表示件数ラベルの色更新
            apply_label_style(count_label, get_color(ThemeKey.TEXT_MUTED), bold=True, point_size=10)

            # データセット選択コンボのQSS更新（色埋め込みのため再適用が必要）
            try:
                combo.setStyleSheet(_build_combo_style())
            except Exception:
                pass
            
            container.update()
        except Exception as e:
            logger.error(f"create_dataset_dropdown_all: テーマ更新エラー: {e}")
    
    container.refresh_theme = refresh_theme

    def reset_filters_to_all(reload=True):
        """全件表示状態に戻してから再読み込み"""
        share_all = share_button_group.button(0) if share_button_group else None
        member_all = member_button_group.button(0) if member_button_group else None
        controls = [
            share_all,
            share_button_group.button(1) if share_button_group else None,
            share_button_group.button(2) if share_button_group else None,
            member_all,
            member_button_group.button(1) if member_button_group else None,
            member_button_group.button(2) if member_button_group else None,
            type_combo,
            grant_edit,
        ]

        blocked = []
        for ctrl in controls:
            if ctrl and hasattr(ctrl, 'blockSignals'):
                try:
                    previous = ctrl.blockSignals(True)
                except Exception:
                    continue
                blocked.append((ctrl, previous))

        changed = False
        try:
            if share_all and hasattr(share_all, 'isChecked') and not share_all.isChecked():
                share_all.setChecked(True)
                changed = True
            if member_all and hasattr(member_all, 'isChecked') and not member_all.isChecked():
                member_all.setChecked(True)
                changed = True
            if type_combo and hasattr(type_combo, 'currentIndex') and type_combo.currentIndex() != 0:
                type_combo.setCurrentIndex(0)
                changed = True
            if grant_edit and hasattr(grant_edit, 'text') and grant_edit.text().strip():
                grant_edit.clear()
                changed = True
        finally:
            for ctrl, previous in blocked:
                try:
                    ctrl.blockSignals(previous)
                except Exception:
                    pass

        if reload:
            try:
                load_and_filter_datasets()
            except Exception:
                logger.debug("reset_filters_to_all: reload failed", exc_info=True)
        return changed

    container.reset_filters = reset_filters_to_all
    container.reload_datasets = load_and_filter_datasets
    
    # ThemeManager 接続
    # NOTE:
    # - テーマ変更シグナルにローカル関数(クロージャ)を直接 connect すると、
    #   破棄済みWidget参照が残ったり、disconnect が漏れた場合にシグナル受信が蓄積しやすい。
    # - QObject 子のブリッジを介して connect し、container 破棄と同時に自動的に解除されるようにする。
    try:
        from PySide6.QtCore import QObject, Slot
        from classes.theme.theme_manager import ThemeManager

        theme_manager = ThemeManager.instance()

        class _ThemeChangedBridge(QObject):
            @Slot(object)
            def on_theme_changed(self, *_args):
                try:
                    refresh_theme()
                except Exception:
                    pass

        container._rde_theme_changed_bridge = _ThemeChangedBridge(container)  # type: ignore[attr-defined]
        theme_manager.theme_changed.connect(container._rde_theme_changed_bridge.on_theme_changed)  # type: ignore[attr-defined]
    except Exception:
        pass
    
    return container

def create_data_fetch2_widget(parent=None, bearer_token=None):
    # 非同期化を解除（QThread, Workerクラス削除）
    """
    データ取得2用ウィジェット（dataset.json参照・検索付きドロップダウン）
    """
    widget = QWidget(parent)
    layout = QVBoxLayout(widget)
    try:
        layout.setAlignment(Qt.AlignTop)
    except Exception:
        pass

    # dataset.jsonのパス
    dataset_json_path = get_dynamic_file_path('output/rde/data/dataset.json')

    # dataset.jsonの絶対パスを表示
    dataset_json_abspath = os.path.abspath(dataset_json_path)

    from qt_compat.widgets import QSizePolicy
    path_label = QLabel(f"dataset.jsonパス: {dataset_json_abspath}")
    path_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 9pt; padding: 0px 0px;")
    path_label.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
    layout.addWidget(path_label)

    # ファイルフィルタ状態表示ラベルを追加（パスの直下に配置）
    filter_status_label = QLabel("📋 ファイルフィルタ: 読み込み中...")
    filter_status_label.setStyleSheet(f"""
        background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
        color: {get_color(ThemeKey.TEXT_PRIMARY)};
        padding: 8px 12px;
        border-radius: 4px;
        border: 1px solid {get_color(ThemeKey.PANEL_BORDER)};
        font-size: 12px;
    """)
    filter_status_label.setWordWrap(True)
    filter_status_label.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
    layout.addWidget(filter_status_label)
    
    # 広域シェアフィルタ付きデータセットドロップダウンを作成（フィルタ表示の下に配置）
    fetch2_dropdown_widget = create_dataset_dropdown_all(dataset_json_path, widget, global_share_filter="both")
    layout.addWidget(fetch2_dropdown_widget)

    launch_controls = QWidget()
    launch_controls_layout = QHBoxLayout()
    launch_controls_layout.setContentsMargins(0, 0, 0, 0)
    launch_label = QLabel("他機能連携:")
    apply_label_style(launch_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    launch_controls_layout.addWidget(launch_label)

    from classes.utils.launch_ui_styles import get_launch_button_style

    launch_button_style = get_launch_button_style()

    launch_targets = [
        ("dataset_edit", "データセット修正"),
        ("dataset_dataentry", "データエントリー"),
        ("data_register", "データ登録"),
        ("data_register_batch", "データ登録(一括)"),
    ]

    launch_buttons = []

    def _dataset_combo():
        return getattr(fetch2_dropdown_widget, 'dataset_dropdown', None)

    def _has_dataset_selection() -> bool:
        combo = _dataset_combo()
        if combo is None:
            return False
        idx = combo.currentIndex()
        if idx < 0:
            return False
        data = combo.itemData(idx)
        if isinstance(data, dict):
            return bool(data.get('id') or data)
        return bool(data)

    def _update_launch_button_state() -> None:
        enabled = _has_dataset_selection()
        for button in launch_buttons:
            button.setEnabled(enabled)

    def _load_dataset_record(dataset_id: str):
        try:
            with open(dataset_json_path, 'r', encoding='utf-8') as f:
                dataset_data = json.load(f)
            items = dataset_data['data'] if isinstance(dataset_data, dict) and 'data' in dataset_data else dataset_data
            for dataset in items or []:
                if isinstance(dataset, dict) and dataset.get('id') == dataset_id:
                    return dataset
        except Exception as exc:
            logger.debug("データセット読み込みに失敗: %s", exc)
        return None

    def _get_current_dataset_payload():
        combo = getattr(fetch2_dropdown_widget, 'dataset_dropdown', None)
        if combo is None:
            return None
        idx = combo.currentIndex()
        if idx < 0:
            safe_show_message_widget(widget, "データセット未選択", "連携するデータセットを選択してください。", "warning")
            return None
        dataset_item_data = combo.itemData(idx)
        dataset_id = dataset_item_data
        if isinstance(dataset_item_data, dict):
            dataset_id = dataset_item_data.get("id")
        if not dataset_id:
            safe_show_message_widget(widget, "データセット未選択", "連携するデータセットを選択してください。", "warning")
            return None
        display_text = combo.itemText(idx)
        dataset_map = getattr(fetch2_dropdown_widget, 'dataset_map', {}) or {}
        raw_dataset = dataset_map.get(dataset_id)
        if raw_dataset is None:
            raw_dataset = _load_dataset_record(dataset_id)
            if raw_dataset:
                dataset_map[dataset_id] = raw_dataset
                fetch2_dropdown_widget.dataset_map = dataset_map
        return {
            "dataset_id": dataset_id,
            "display_text": display_text or dataset_id,
            "raw_dataset": raw_dataset,
        }

    def _handle_launch_request(target_key: str):
        payload = _get_current_dataset_payload()
        if not payload:
            return

        # デバッグ用: 呼び出し元(data_fetch2)が送る dataset_id を明示的にログへ出す
        manager = DatasetLaunchManager.instance()
        dataset_id = payload.get("dataset_id")
        display_text = payload.get("display_text")

        pending_before = getattr(manager, "_pending_request", None)
        receivers_before = getattr(manager, "_receivers", None)
        ui_controller_before = getattr(manager, "_ui_controller", None)
        receivers_keys = sorted(receivers_before.keys()) if isinstance(receivers_before, dict) else []
        pending_target = pending_before.get("target") if isinstance(pending_before, dict) else None
        pending_payload = pending_before.get("payload") if isinstance(pending_before, dict) else None
        pending_id = pending_payload.id if isinstance(pending_payload, DatasetPayload) else None

        logger.info(
            "data_fetch2: launch request target=%s dataset_id=%s display=%s manager_id=%s ui_controller=%s receivers=%s pending=%s:%s",
            target_key,
            dataset_id,
            display_text,
            hex(id(manager)),
            bool(ui_controller_before),
            receivers_keys,
            pending_target or "-",
            pending_id or "-",
        )

        try:
            applied = manager.request_launch(
                target_key=target_key,
                dataset_id=payload["dataset_id"],
                display_text=payload["display_text"],
                raw_dataset=payload["raw_dataset"],
                source_name="data_fetch2",
            )
        except Exception:
            logger.exception(
                "data_fetch2: request_launch failed target=%s dataset_id=%s",
                target_key,
                dataset_id,
            )
            return

        pending_after = getattr(manager, "_pending_request", None)
        pending_after_target = pending_after.get("target") if isinstance(pending_after, dict) else None
        pending_after_payload = pending_after.get("payload") if isinstance(pending_after, dict) else None
        pending_after_id = pending_after_payload.id if isinstance(pending_after_payload, DatasetPayload) else None

        logger.info(
            "data_fetch2: launch result applied=%s pending_after=%s:%s",
            applied,
            pending_after_target or "-",
            pending_after_id or "-",
        )

    for target_key, caption in launch_targets:
        btn = QPushButton(caption)
        btn.setStyleSheet(launch_button_style)
        btn.clicked.connect(lambda _=None, key=target_key: _handle_launch_request(key))
        launch_controls_layout.addWidget(btn)
        launch_buttons.append(btn)

    def _launch_to_subgroup_edit() -> None:
        payload = _get_current_dataset_payload()
        if not payload:
            return
        try:
            from classes.utils.subgroup_launch_helper import launch_to_subgroup_edit

            launch_to_subgroup_edit(
                owner_widget=widget,
                dataset_id=str(payload.get("dataset_id") or ""),
                raw_dataset=payload.get("raw_dataset"),
                source_name="data_fetch2",
            )
        except Exception:
            logger.debug("data_fetch2: launch_to_subgroup_edit failed", exc_info=True)

    subgroup_btn = QPushButton("サブグループ閲覧・修正")
    subgroup_btn.setStyleSheet(launch_button_style)
    subgroup_btn.clicked.connect(_launch_to_subgroup_edit)
    launch_controls_layout.addWidget(subgroup_btn)
    launch_buttons.append(subgroup_btn)

    launch_controls_layout.addStretch()
    launch_controls.setLayout(launch_controls_layout)
    layout.addWidget(launch_controls)
    widget._dataset_launch_buttons = launch_buttons  # type: ignore[attr-defined]

    combo_for_buttons = _dataset_combo()
    if combo_for_buttons is not None:
        combo_for_buttons.currentIndexChanged.connect(lambda *_: _update_launch_button_state())
    _update_launch_button_state()

    # ウィジェットにフィルタ状態ラベルを保存（後で更新できるように）
    widget.filter_status_label = filter_status_label
    
    # 初期フィルタ状態を表示
    def update_filter_status_display():
        """フィルタ状態表示を更新"""
        try:
            # 親ウィジェット（DataFetch2TabWidget）からフィルタ設定を取得
            parent_tab_widget = widget.parent()
            from classes.data_fetch2.conf.file_filter_config import get_default_filter
            from classes.data_fetch2.util.file_filter_util import get_filter_summary
            if parent_tab_widget and hasattr(parent_tab_widget, 'current_filter_config') and parent_tab_widget.current_filter_config:
                filter_config = parent_tab_widget.current_filter_config
            else:
                # 初期状態でもデフォルトフィルタを表示して未適用を明示
                filter_config = get_default_filter()
            summary = get_filter_summary(filter_config)
            filter_status_label.setText(f"📋 ファイルフィルタ: {summary}")
            filter_status_label.setToolTip(f"ファイルフィルタタブで設定された条件:\n{summary}")
        except Exception as e:
            logger.debug(f"フィルタ状態表示更新エラー: {e}")
            filter_status_label.setText("📋 ファイルフィルタ: 設定を確認できません")

    def set_filter_config_for_display(filter_config):
        """親経由でなく直接フィルタ設定を受け取り表示を更新"""
        try:
            from classes.data_fetch2.util.file_filter_util import get_filter_summary
            summary = get_filter_summary(filter_config or {})
            filter_status_label.setText(f"📋 ファイルフィルタ: {summary}")
            filter_status_label.setToolTip(f"ファイルフィルタタブで設定された条件:\n{summary}")
        except Exception as e:
            logger.debug(f"直接表示更新エラー: {e}")
            filter_status_label.setText("📋 ファイルフィルタ: 設定を確認できません")
    
    # ウィジェットに更新関数を保存
    widget.update_filter_status_display = update_filter_status_display
    widget.set_filter_config_for_display = set_filter_config_for_display
    
    # 初回表示更新（少し遅延させてタブ構築完了後に実行）
    # 初期表示更新はタブ側のinit_filter_stateで実施するためここではタイマー更新を行わない

    # 選択中データセットのファイルリストを取得するボタン
    fetch_files_btn = QPushButton("選択したデータセットのファイルを一括取得")
    fetch_files_btn.setStyleSheet(f"""
        background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
        color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
        font-weight: bold;
        font-size: 13px;
        padding: 8px 16px;
        border-radius: 6px;
    """)
    layout.addWidget(fetch_files_btn)

    # テーマ切替時にこのウィジェット内の「個別styleSheet埋め込み」を再適用（更新漏れ対策）
    def _refresh_theme_local(*_args):
        try:
            path_label.setStyleSheet(
                f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 9pt; padding: 0px 0px;"
            )
        except Exception:
            pass

        try:
            filter_status_label.setStyleSheet(f"""
                background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                padding: 8px 12px;
                border-radius: 4px;
                border: 1px solid {get_color(ThemeKey.PANEL_BORDER)};
                font-size: 12px;
            """)
        except Exception:
            pass

        try:
            apply_label_style(launch_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
        except Exception:
            pass

        try:
            new_launch_button_style = get_launch_button_style()
            for b in launch_buttons:
                b.setStyleSheet(new_launch_button_style)
        except Exception:
            pass

        try:
            fetch_files_btn.setStyleSheet(f"""
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                font-weight: bold;
                font-size: 13px;
                padding: 8px 16px;
                border-radius: 6px;
            """)
        except Exception:
            pass

        try:
            summary_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-size: 11px;")
        except Exception:
            pass

    # ThemeManager 接続（widget 破棄時に自動解除されるよう QObject ブリッジ経由）
    try:
        from PySide6.QtCore import QObject, Slot
        from classes.theme.theme_manager import ThemeManager

        tm = ThemeManager.instance()

        class _ThemeChangedBridge(QObject):
            @Slot(object)
            def on_theme_changed(self, *_args):
                try:
                    _refresh_theme_local()
                except Exception:
                    pass

        widget._rde_theme_changed_bridge = _ThemeChangedBridge(widget)  # type: ignore[attr-defined]
        tm.theme_changed.connect(widget._rde_theme_changed_bridge.on_theme_changed)  # type: ignore[attr-defined]
    except Exception:
        pass

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
                    progress_dialog.setWindowTitle("ファイル一括取得")
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
                        """プログレス更新（メインスレッドで実行）"""
                        if progress_dialog and not progress_dialog.wasCanceled():
                            progress_dialog.setValue(value)
                            progress_dialog.setLabelText(message)
                            # repaint()を呼び出してUI更新を即座に反映
                            progress_dialog.repaint()
                    
                    # 完了時の処理
                    def on_finished(success, message):
                        def handle_finished():
                            if progress_dialog:
                                progress_dialog.close()
                            if success:
                                logger.info(f"ファイル取得処理完了: dataset_id={dataset_obj}, message_len={len(message) if isinstance(message, str) else 'N/A'}")
                                logger.info(f"完了メッセージ詳細\n---\n{message}\n---")
                                # 表示メッセージ
                                if message and message != "no_data":
                                    dialog_text = message
                                    dialog_title = "完了"
                                elif message == "no_data":
                                    dialog_text = "選択されたデータセットにはデータエントリがありませんでした"
                                    dialog_title = "情報"
                                else:
                                    # フォールバックでも最低限の件数を表示する
                                    dialog_title = "完了"
                                    dialog_text = "ファイル一括取得が完了しました"
                                    try:
                                        from classes.data_fetch2.core.logic.fetch2_filelist_logic import get_dataset_filetype_counts
                                        # 可能なら直前選択のdataset_idで再集計
                                        combo = getattr(fetch2_dropdown_widget, 'dataset_dropdown', None)
                                        dsid = combo.itemData(combo.currentIndex()) if combo else None
                                        from core.bearer_token_manager import BearerTokenManager
                                        token_fb = BearerTokenManager.get_token_with_relogin_prompt(parent)
                                        counts_fb = get_dataset_filetype_counts({"id": dsid, "attributes": {}}, token_fb, None) if (dsid and token_fb) else {}
                                        total_fb = sum(counts_fb.values())
                                        parts_fb = [f"{k}: {v}" for k, v in sorted(counts_fb.items())]
                                        inner_fb = "、".join(parts_fb) if parts_fb else "対象ファイルなし"
                                        dialog_text = f"ファイル一括取得が完了しました\n合計ダウンロード予定ファイル: {total_fb}件\n内訳（fileType別）: {inner_fb}"
                                    except Exception:
                                        pass

                                # 保存先フォルダ（fetch_files_json_for_dataset と同じ規約）
                                save_folder = None
                                try:
                                    from config.common import get_dynamic_file_path
                                    from classes.data_fetch2.core.logic.fetch2_filelist_logic import replace_invalid_path_chars
                                    import os

                                    attrs = (dataset_obj or {}).get('attributes', {}) or {}
                                    grant_number = str(attrs.get('grantNumber') or '').strip() or "不明"
                                    dataset_name = str(attrs.get('name') or '').strip() or "データセット名未設定"
                                    safe_dataset_name = replace_invalid_path_chars(dataset_name)
                                    candidate = get_dynamic_file_path(f"output/rde/data/dataFiles/{grant_number}/{safe_dataset_name}")
                                    if os.path.isdir(candidate):
                                        save_folder = candidate
                                    else:
                                        base = get_dynamic_file_path("output/rde/data/dataFiles")
                                        if os.path.isdir(base):
                                            save_folder = base
                                except Exception:
                                    save_folder = None

                                # ボタン付き完了ダイアログ（保存フォルダを開く）
                                try:
                                    from qt_compat.widgets import QMessageBox
                                    msg_box = QMessageBox(widget)
                                    msg_box.setWindowTitle(dialog_title)
                                    msg_box.setText(dialog_text)
                                    msg_box.setIcon(QMessageBox.Information)
                                    open_btn = msg_box.addButton("📂 保存フォルダを開く", QMessageBox.ActionRole)
                                    ok_btn = msg_box.addButton(QMessageBox.Ok)
                                    if not save_folder:
                                        try:
                                            open_btn.setEnabled(False)
                                        except Exception:
                                            pass
                                    msg_box.exec()
                                    if save_folder and msg_box.clickedButton() == open_btn:
                                        try:
                                            from qt_compat.gui import QDesktopServices
                                            from qt_compat.core import QUrl
                                            QDesktopServices.openUrl(QUrl.fromLocalFile(save_folder))
                                        except Exception:
                                            try:
                                                import os
                                                os.startfile(str(save_folder))
                                            except Exception:
                                                pass
                                except Exception:
                                    # フォールバック
                                    safe_show_message_widget(widget, dialog_title, dialog_text, "information")
                            else:
                                logger.error(f"ファイル取得処理失敗: dataset_id={dataset_obj}, error={message}")
                                logger.error(f"失敗メッセージ詳細\n---\n{message}\n---")
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

    # ダウンロード予定内訳の表示ラベル
    summary_label = QLabel("📦 ダウンロード予定内訳: 未選択")
    summary_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-size: 11px;")

    # 内訳テキストは非同期に更新されるため、テキスト変更に伴うラベルの高さ変化が
    # スクロールバーの長さを「じわじわ」変化させないよう、表示領域を先に確保しておく。
    try:
        from qt_compat.widgets import QSizePolicy

        summary_label.setWordWrap(True)
        summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        line_h = int(summary_label.fontMetrics().lineSpacing())
        # 2行ぶん確保（詳細が長くてもUI全体の高さは変化しない）
        summary_label.setMinimumHeight(line_h * 2)
        summary_label.setMaximumHeight(line_h * 2)
    except Exception:
        pass

    layout.addWidget(summary_label)
    try:
        widget.planned_summary_label = summary_label
    except Exception:
        pass

    # シグナル接続は1回だけ（update_planned_summaryごとにconnectすると多重接続で更新が増幅する）
    try:
        if not getattr(widget, "_planned_summary_signal_connected", False):
            _summary_signal.update_text.connect(summary_label.setText)
            widget._planned_summary_signal_connected = True
    except Exception:
        pass

    # 古いスレッド結果の反映を防ぐための世代管理
    try:
        if not hasattr(widget, "_planned_summary_request_id"):
            widget._planned_summary_request_id = 0
    except Exception:
        pass

    def update_planned_summary():
        try:
            try:
                widget._planned_summary_request_id = int(getattr(widget, "_planned_summary_request_id", 0)) + 1
                request_id = widget._planned_summary_request_id
            except Exception:
                request_id = None

            try:
                from shiboken6 import isValid as _qt_is_valid
            except Exception:
                _qt_is_valid = None

            def _safe_emit_update_text(text: str) -> None:
                try:
                    if request_id is not None and getattr(widget, "_planned_summary_request_id", None) != request_id:
                        return
                except Exception:
                    pass

                try:
                    if _qt_is_valid is not None and not _qt_is_valid(widget):
                        return
                except Exception:
                    pass

                try:
                    if _qt_is_valid is not None and not _qt_is_valid(_summary_signal):
                        return
                except Exception:
                    pass

                try:
                    _summary_signal.update_text.emit(text)
                except RuntimeError:
                    # Widget teardown / interpreter shutdown などで QObject が破棄済みのケース。
                    return
                except Exception:
                    try:
                        summary_label.setText(text)
                    except Exception:
                        pass

            combo = getattr(fetch2_dropdown_widget, 'dataset_dropdown', None)
            if not combo or combo.currentIndex() < 0:
                summary_label.setText("📦 ダウンロード予定内訳: 未選択")
                return
            dataset_id = combo.itemData(combo.currentIndex())
            if not dataset_id:
                summary_label.setText("📦 ダウンロード予定内訳: 未選択")
                return

            # 非同期集計中であることを明示（後でテキストが更新されても高さは固定）
            _safe_emit_update_text("📦 ダウンロード予定内訳: 集計中…")

            # Bearer Token取得
            from core.bearer_token_manager import BearerTokenManager
            token = BearerTokenManager.get_token_with_relogin_prompt(parent)
            if not token:
                summary_label.setText("📦 ダウンロード予定内訳: 認証が必要です")
                return

            # 別スレッドでAPI集計してUI更新
            from threading import Thread
            def worker():
                try:
                    # dataset.json から選択データセットオブジェクトを取得
                    ds_obj = None
                    try:
                        with open(dataset_json_path, 'r', encoding='utf-8') as f:
                            dataset_data = json.load(f)
                        items = dataset_data['data'] if isinstance(dataset_data, dict) and 'data' in dataset_data else dataset_data
                        for d in items or []:
                            if isinstance(d, dict) and d.get('id') == dataset_id:
                                ds_obj = d
                                break
                    except Exception:
                        ds_obj = None
                    from classes.data_fetch2.core.logic.fetch2_filelist_logic import get_dataset_filetype_counts
                    # 親タブのフィルタ（あれば適用）
                    file_filter_config = None
                    try:
                        parent_obj = widget.parent()
                        while parent_obj:
                            if hasattr(parent_obj, 'current_filter_config'):
                                file_filter_config = parent_obj.current_filter_config
                                break
                            parent_obj = parent_obj.parent()
                    except Exception:
                        file_filter_config = None
                    logger.info(f"内訳更新開始: dataset_id={dataset_id}, filter={file_filter_config}")
                    counts = get_dataset_filetype_counts(ds_obj or {"id": dataset_id, "attributes": {}}, token, file_filter_config)
                    total = sum(counts.values())
                    parts = [f"{k}: {v}" for k, v in sorted(counts.items()) if v > 0]
                    text = "、".join(parts) if parts else "対象ファイルなし"
                    logger.info(f"内訳更新完了: total={total}, detail={text}")
                    new_text = f"📦 ダウンロード予定内訳: 合計 {total} 件({text})"
                    # シグナル経由でメインスレッドに確実に更新（テスト/終了処理では破棄済みの場合がある）
                    _safe_emit_update_text(new_text)
                except Exception as e:
                    logger.warning(f"内訳更新失敗: {e}")
                    _safe_emit_update_text("📦 ダウンロード予定内訳: 取得に失敗しました")
            
            Thread(target=worker, daemon=True).start()
        except Exception:
            summary_label.setText("📦 ダウンロード予定内訳: 取得に失敗しました")

    # コンボ選択変更で内訳更新
    try:
        def _on_index_changed(idx):
            try:
                dsid = fetch2_dropdown_widget.dataset_dropdown.itemData(idx)
            except Exception:
                dsid = None
            logger.info(f"dataset_dropdown changed: idx={idx}, dataset_id={dsid}")
            update_planned_summary()
        fetch2_dropdown_widget.dataset_dropdown.currentIndexChanged.connect(_on_index_changed)
        logger.info("dataset_dropdown connected to update_planned_summary")
    except Exception:
        pass
    # 初期選択がある場合にも更新を一度実行
    try:
        QTimer.singleShot(0, update_planned_summary)
    except Exception:
        pass

    def _find_dataset_index(dataset_id: str) -> int:
        combo = getattr(fetch2_dropdown_widget, 'dataset_dropdown', None)
        if not combo:
            return -1
        for i in range(combo.count()):
            if combo.itemData(i) == dataset_id:
                return i
        return -1

    def _format_display_text(payload: DatasetPayload) -> str:
        if payload.display_text:
            return payload.display_text
        attrs = (payload.raw or {}).get('attributes', {}) if payload.raw else {}
        grant = attrs.get('grantNumber', '')
        name = attrs.get('name', '')
        parts = [part for part in (grant, name) if part]
        return " - ".join(parts) if parts else payload.id

    def _apply_dataset_payload(payload: DatasetPayload) -> bool:
        if not payload or not payload.id:
            return False
        combo = getattr(fetch2_dropdown_widget, 'dataset_dropdown', None)
        if combo is None:
            return False

        relax_fetch2_filters_for_launch(fetch2_dropdown_widget)

        dataset_map = getattr(fetch2_dropdown_widget, 'dataset_map', {}) or {}
        if payload.raw:
            dataset_map[payload.id] = payload.raw
            fetch2_dropdown_widget.dataset_map = dataset_map

        index = _find_dataset_index(payload.id)
        if index < 0:
            reset_filters = getattr(fetch2_dropdown_widget, 'reset_filters', None)
            reload_fn = getattr(fetch2_dropdown_widget, 'reload_datasets', None)
            if callable(reset_filters):
                reset_filters()
            if callable(reload_fn):
                reload_fn()
                index = _find_dataset_index(payload.id)

        if index < 0:
            display_text = _format_display_text(payload)
            combo.blockSignals(True)
            combo.addItem(display_text, payload.id)
            combo.blockSignals(False)
            index = combo.count() - 1

        if index < 0:
            return False

        previous_index = combo.currentIndex()
        combo.setCurrentIndex(index)
        if previous_index == index:
            try:
                update_planned_summary()
            except Exception:
                logger.debug("data_fetch2: manual summary refresh failed", exc_info=True)
        _update_launch_button_state()
        return True

    DatasetLaunchManager.instance().register_receiver("data_fetch2", _apply_dataset_payload)

    # 余白を下へ押し上げるストレッチで上側に詰める
    layout.addStretch()
    return widget
