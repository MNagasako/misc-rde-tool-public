#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
データ取得2ウィジェット v1.17.0
データセット選択・ファイル一括取得機能

主要機能:
- dataset.json参照による検索付きドロップダウン
- 選択データセットのファイル一括取得
- プログレス表示対応
- 企業プロキシ・SSL証明書対応

変更履歴:
- v1.15.1: プロキシ設定UI改善、PAC・企業CA設定の横並び表示対応
- v1.15.0: ワークスペース整理完了・コードベース品質向上
"""

import os
import logging
import threading
from PyQt5.QtWidgets import QVBoxLayout, QLabel, QWidget, QMessageBox, QProgressDialog
from PyQt5.QtCore import QTimer, Qt, QMetaObject, Q_ARG
from classes.dataset.util.dataset_dropdown_util import create_dataset_dropdown_all
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

def create_data_fetch2_widget(parent=None):
    # 非同期化を解除（QThread, Workerクラス削除）
    """
    データ取得2用ウィジェット（dataset.json参照・検索付きドロップダウン）
    """
    widget = parent if parent is not None else QWidget()
    layout = QVBoxLayout()
    label = QLabel("データ取得2機能")
    label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1976d2; padding: 10px;")
    #layout.addWidget(label)


    # dataset.jsonのパス
    dataset_json_path = os.path.normpath(os.path.join(OUTPUT_DIR, 'rde/data/dataset.json'))
    # info.jsonは不要

    # dataset.jsonの絶対パスを表示
    dataset_json_abspath = os.path.abspath(dataset_json_path)

    path_label = QLabel(f"dataset.jsonパス: {dataset_json_abspath}")
    path_label.setStyleSheet("color: #888; font-size: 9pt; padding: 0px 0px;")
    layout.addWidget(path_label)

    # 広域シェアフィルタ付きデータセットドロップダウンを作成
    fetch2_dropdown_widget = create_dataset_dropdown_all(dataset_json_path, widget, global_share_filter="both")
    layout.addWidget(fetch2_dropdown_widget)

    # 選択中データセットのファイルリストを取得するボタン
    from PyQt5.QtWidgets import QPushButton
    fetch_files_btn = QPushButton("選択したデータセットのファイルを一括取得")
    fetch_files_btn.setStyleSheet(
        "background-color: #1976d2; color: white; font-weight: bold; font-size: 13px; padding: 8px 16px; border-radius: 6px;"
    )
    layout.addWidget(fetch_files_btn)

    # エクスプローラーでdataFilesフォルダを開くボタン
    from PyQt5.QtWidgets import QPushButton
    from PyQt5.QtCore import QUrl
    from PyQt5.QtGui import QDesktopServices
    open_folder_btn = QPushButton("出力フォルダ(dataFiles)をエクスプローラーで開く")
    layout.addWidget(open_folder_btn)

    def on_open_folder():
        QDesktopServices.openUrl(QUrl.fromLocalFile(DATAFILES_DIR))

    open_folder_btn.clicked.connect(on_open_folder)


    def find_bearer_token_recursive(obj):
        # objがNoneなら終了
        if obj is None:
            return None
        # bearer_token属性があれば返す
        if hasattr(obj, 'bearer_token') and getattr(obj, 'bearer_token'):
            return getattr(obj, 'bearer_token')
        # parent属性があれば再帰
        if hasattr(obj, 'parent'):
            return find_bearer_token_recursive(getattr(obj, 'parent'))
        return None

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
            dataset_obj = combo.itemData(idx)
            logger.info(f"選択されたデータセット: index={idx}, dataset_id={dataset_obj}")

            # データセットが選択されているかチェック
            if dataset_obj is None or not dataset_obj:
                logger.warning("データセットが選択されていません")
                safe_show_message_widget(widget, "選択エラー", "データセットを選択してください。", "warning")
                return

            # トークン取得（親→親→...でbearer_token探索）
            bearer_token = find_bearer_token_recursive(parent)
            if not bearer_token:
                logger.error("認証トークンが取得できません")
                safe_show_message_widget(widget, "認証エラー", "認証トークンが取得できません。bearer_token属性がどの親にもありません。", "warning")
                return

            # プログレス表示付きでファイル取得処理を実行
            def show_fetch_progress():
                """プログレス表示付きファイル取得"""
                try:
                    from PyQt5.QtWidgets import QProgressDialog, QMessageBox
                    from PyQt5.QtCore import QTimer, Qt
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
                    worker = ProgressWorker(
                        fetch_files_json_for_dataset,
                        task_args=[widget, dataset_obj, bearer_token],
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

    widget.setLayout(layout)
    return widget
