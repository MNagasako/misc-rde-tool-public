"""
トークン状態表示タブ - ARIM RDE Tool
Bearer Tokenの状態確認・手動リフレッシュ機能

機能:
- 複数ホストのトークン一覧表示（RDE/Material API）
- 有効期限表示（残り時間）
- 最終更新日時表示
- 手動リフレッシュボタン
- 自動リフレッシュON/OFF切替
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

# ログ設定
logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
        QPushButton, QMessageBox, QLabel, QCheckBox, QHeaderView,
        QGroupBox, QProgressBar, QFrame
    )
    from qt_compat.core import Qt, QTimer
    from qt_compat.gui import QFont, QColor
    PYQT5_AVAILABLE = True
except ImportError as e:
    logger.error(f"Qt互換レイヤーインポート失敗: {e}")
    PYQT5_AVAILABLE = False
    class QWidget: pass

from classes.managers.token_manager import TokenManager, TokenData


class TokenStatusTab(QWidget):
    """トークン状態表示タブ"""
    
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.parent_widget = parent
        self.token_manager = TokenManager.get_instance()  # シングルトン取得
        
        # UI構築
        self.setup_ui()
        
        # TokenManagerシグナル接続
        self.token_manager.token_refreshed.connect(self.on_token_refreshed)
        self.token_manager.token_refresh_failed.connect(self.on_token_refresh_failed)
        self.token_manager.token_expired.connect(self.on_token_expired)
        
        # 自動更新タイマー（1分ごとに表示更新）
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.refresh_display)
        self.update_timer.start(60000)  # 60秒
        
        # 初期データ読み込み
        self.refresh_display()
    
    def setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # タイトル
        title_label = QLabel("Bearer Token 状態管理")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        info_label = QLabel(
            "現在保存されているBearer Tokenの状態を確認できます。\n"
            "トークンの有効期限が近づいている場合は、手動でリフレッシュできます。"
        )
        layout.addWidget(info_label)
        
        # 自動リフレッシュ制御
        self.setup_auto_refresh_control(layout)
        
        # トークン一覧テーブル
        self.setup_token_table(layout)
        
        # ボタンエリア
        self.setup_buttons(layout)
        
        layout.addStretch()
    
    def setup_auto_refresh_control(self, parent_layout):
        """自動リフレッシュ制御UI"""
        group = QGroupBox("自動リフレッシュ設定")
        layout = QHBoxLayout()
        group.setLayout(layout)
        
        self.auto_refresh_checkbox = QCheckBox("自動リフレッシュを有効化")
        self.auto_refresh_checkbox.setChecked(True)  # デフォルトON
        self.auto_refresh_checkbox.stateChanged.connect(self.toggle_auto_refresh)
        layout.addWidget(self.auto_refresh_checkbox)
        
        info_label = QLabel("（有効期限の5分前に自動更新）")
        info_label.setStyleSheet("color: gray;")
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        parent_layout.addWidget(group)
    
    def setup_token_table(self, parent_layout):
        """トークン一覧テーブル"""
        self.token_table = QTableWidget()
        self.token_table.setColumnCount(5)
        self.token_table.setHorizontalHeaderLabels([
            "ホスト名", "有効期限", "残り時間", "最終更新", "操作"
        ])
        
        # カラム幅調整
        header = self.token_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # ホスト名
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 有効期限
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 残り時間
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 最終更新
        header.setSectionResizeMode(4, QHeaderView.Fixed)  # 操作
        self.token_table.setColumnWidth(4, 100)
        
        # 行選択モード
        self.token_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.token_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        parent_layout.addWidget(self.token_table)
    
    def setup_buttons(self, parent_layout):
        """ボタンエリア"""
        button_layout = QHBoxLayout()
        
        self.refresh_display_button = QPushButton("表示更新")
        self.refresh_display_button.clicked.connect(self.refresh_display)
        button_layout.addWidget(self.refresh_display_button)
        
        self.refresh_all_button = QPushButton("全トークンリフレッシュ")
        self.refresh_all_button.clicked.connect(self.refresh_all_tokens)
        button_layout.addWidget(self.refresh_all_button)
        
        button_layout.addStretch()
        
        parent_layout.addLayout(button_layout)
    
    def refresh_display(self):
        """表示更新（v2.0.3: 2ホスト固定表示 - TokenManager.ACTIVE_HOSTS使用）"""
        try:
            # トークンファイル読み込み
            tokens = self.token_manager._load_all_tokens()
            
            # テーブルクリア
            self.token_table.setRowCount(0)
            
            # v2.0.3: TokenManagerのクラス定数を使用（必ず表示する2つのホスト）
            for host in self.token_manager.ACTIVE_HOSTS:
                if host in tokens:
                    # トークンが存在する場合
                    try:
                        token_data = TokenData.from_dict(tokens[host])
                        self.add_token_row(host, token_data)
                    except Exception as e:
                        logger.error(f"トークンデータ解析エラー ({host}): {e}")
                        # エラーでも行は表示
                        self.add_empty_token_row(host, "データエラー")
                else:
                    # トークンが存在しない場合も行を表示
                    self.add_empty_token_row(host, "未取得")
        
        except Exception as e:
            logger.error(f"表示更新エラー: {e}", exc_info=True)
            QMessageBox.warning(self, "エラー", f"トークン情報の取得に失敗しました: {e}")
    
    def add_token_row(self, host: str, token_data: TokenData):
        """トークン行追加"""
        row = self.token_table.rowCount()
        self.token_table.insertRow(row)
        
        # ホスト名
        host_item = QTableWidgetItem(host)
        self.token_table.setItem(row, 0, host_item)
        
        # 有効期限
        try:
            expires_dt = datetime.fromisoformat(token_data.expires_at.replace('Z', '+00:00'))
            expires_str = expires_dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            expires_str = token_data.expires_at
        
        expires_item = QTableWidgetItem(expires_str)
        self.token_table.setItem(row, 1, expires_item)
        
        # 残り時間（プログレスバー）
        self.set_remaining_time_cell(row, 2, token_data)
        
        # 最終更新
        try:
            updated_dt = datetime.fromisoformat(token_data.updated_at.replace('Z', '+00:00'))
            updated_str = updated_dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            updated_str = token_data.updated_at
        
        updated_item = QTableWidgetItem(updated_str)
        self.token_table.setItem(row, 3, updated_item)
        
        # 手動リフレッシュボタン
        refresh_button = QPushButton("リフレッシュ")
        refresh_button.clicked.connect(lambda checked, h=host: self.refresh_token(h))
        self.token_table.setCellWidget(row, 4, refresh_button)
    
    def add_empty_token_row(self, host: str, status: str):
        """トークン未取得行追加（v2.0.3新規）"""
        row = self.token_table.rowCount()
        self.token_table.insertRow(row)
        
        # ホスト名
        host_item = QTableWidgetItem(host)
        self.token_table.setItem(row, 0, host_item)
        
        # 有効期限
        status_item = QTableWidgetItem(status)
        status_item.setForeground(QColor("red"))
        self.token_table.setItem(row, 1, status_item)
        
        # 残り時間
        empty_item = QTableWidgetItem("-")
        self.token_table.setItem(row, 2, empty_item)
        
        # 最終更新
        empty_item2 = QTableWidgetItem("-")
        self.token_table.setItem(row, 3, empty_item2)
        
        # ボタンは無効化
        refresh_button = QPushButton("取得必要")
        refresh_button.setEnabled(False)
        self.token_table.setCellWidget(row, 4, refresh_button)
    
    def set_remaining_time_cell(self, row: int, col: int, token_data: TokenData):
        """残り時間セル設定（プログレスバー）"""
        try:
            expires_dt = datetime.fromisoformat(token_data.expires_at.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            remaining = expires_dt - now
            
            if remaining.total_seconds() <= 0:
                # 期限切れ
                label = QLabel("期限切れ")
                label.setStyleSheet("color: red; font-weight: bold;")
                self.token_table.setCellWidget(row, col, label)
            else:
                # 残り時間表示
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                
                # プログレスバーで視覚化（1時間=100%想定）
                max_seconds = 3600  # 1時間
                progress = min(100, int((remaining.total_seconds() / max_seconds) * 100))
                
                progress_bar = QProgressBar()
                progress_bar.setMaximum(100)
                progress_bar.setValue(progress)
                progress_bar.setFormat(f"{hours}時間{minutes}分")
                
                # 警告色設定
                if remaining.total_seconds() < 600:  # 10分以内
                    progress_bar.setStyleSheet("QProgressBar::chunk { background-color: red; }")
                elif remaining.total_seconds() < 1800:  # 30分以内
                    progress_bar.setStyleSheet("QProgressBar::chunk { background-color: orange; }")
                
                self.token_table.setCellWidget(row, col, progress_bar)
        
        except Exception as e:
            logger.error(f"残り時間計算エラー: {e}")
            error_item = QTableWidgetItem("エラー")
            self.token_table.setItem(row, col, error_item)
    
    def refresh_token(self, host: str):
        """手動トークンリフレッシュ"""
        try:
            logger.info(f"手動トークンリフレッシュ開始: {host}")
            
            # リフレッシュ実行
            success = self.token_manager.refresh_access_token(host)
            
            if success:
                QMessageBox.information(self, "成功", f"{host}のトークンをリフレッシュしました")
                self.refresh_display()
            else:
                QMessageBox.warning(self, "失敗", f"{host}のトークンリフレッシュに失敗しました")
        
        except Exception as e:
            logger.error(f"手動リフレッシュエラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"トークンリフレッシュエラー: {e}")
    
    def refresh_all_tokens(self):
        """全トークンリフレッシュ"""
        try:
            tokens = self.token_manager._load_all_tokens()
            
            if not tokens:
                QMessageBox.information(self, "情報", "リフレッシュ対象のトークンがありません")
                return
            
            # 確認ダイアログ
            reply = QMessageBox.question(
                self, "確認",
                f"{len(tokens)}個のトークンをリフレッシュしますか？",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                return
            
            # 各トークンをリフレッシュ
            success_count = 0
            fail_count = 0
            
            for host in tokens.keys():
                try:
                    if self.token_manager.refresh_access_token(host):
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    logger.error(f"リフレッシュエラー ({host}): {e}")
                    fail_count += 1
            
            # 結果表示
            QMessageBox.information(
                self, "完了",
                f"リフレッシュ完了\n成功: {success_count}件\n失敗: {fail_count}件"
            )
            
            self.refresh_display()
        
        except Exception as e:
            logger.error(f"全トークンリフレッシュエラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"リフレッシュエラー: {e}")
    
    def toggle_auto_refresh(self, state):
        """自動リフレッシュON/OFF切替"""
        if state == 2:  # Qt.CheckState.Checked.value
            self.token_manager.start_auto_refresh()
            logger.info("自動リフレッシュ有効化")
        else:
            self.token_manager.stop_auto_refresh()
            logger.info("自動リフレッシュ無効化")
    
    # TokenManagerシグナルハンドラ
    def on_token_refreshed(self, host: str):
        """トークンリフレッシュ成功"""
        logger.info(f"トークンリフレッシュ成功通知: {host}")
        self.refresh_display()
    
    def on_token_refresh_failed(self, host: str, error: str):
        """トークンリフレッシュ失敗"""
        logger.warning(f"トークンリフレッシュ失敗通知: {host} - {error}")
        QMessageBox.warning(self, "リフレッシュ失敗", f"{host}のトークンリフレッシュに失敗しました: {error}")
    
    def on_token_expired(self, host: str):
        """トークン期限切れ"""
        logger.error(f"トークン期限切れ通知: {host}")
        QMessageBox.critical(
            self, "トークン期限切れ",
            f"{host}のトークンが期限切れです。再ログインが必要です。"
        )
        self.refresh_display()
