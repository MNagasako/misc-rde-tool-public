#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
プロキシ起動時通知ダイアログ
アプリケーション起動時にプロキシ設定の判断結果をユーザーに通知

移行済み: src/widgets → src/classes/config/ui
"""

import sys
import os

# パス設定
try:
    from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QIcon, QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    # ダミークラス
    class QDialog: pass

import yaml
from config.common import get_dynamic_file_path, get_static_resource_path

class ProxyStartupNotificationDialog(QDialog):
    """プロキシ起動時通知ダイアログ"""
    
    def __init__(self, proxy_config, parent=None):
        if not PYQT5_AVAILABLE:
            return
            
        super().__init__(parent)
        self.proxy_config = proxy_config
        self.init_ui()
        
    def init_ui(self):
        """UI初期化"""
        if not PYQT5_AVAILABLE:
            return
            
        self.setWindowTitle("プロキシ設定通知")
        self.setFixedSize(500, 300)
        self.setWindowModality(Qt.ApplicationModal)
        
        # アイコン設定
        try:
            icon_path = get_static_resource_path("image/icon/icon1.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except:
            pass
        
        layout = QVBoxLayout()
        
        # タイトル
        title_label = QLabel("🌐 プロキシ設定の起動時判断結果")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 判断結果の表示
        self._add_proxy_status_info(layout)
        
        # 設定変更リンク
        self._add_settings_info(layout)
        
        # チェックボックス（今後の表示制御）
        self.dont_show_again_checkbox = QCheckBox("今後この通知を表示しない")
        layout.addWidget(self.dont_show_again_checkbox)
        
        # ボタン
        button_layout = QHBoxLayout()
        
        self.settings_button = QPushButton("プロキシ設定を変更")
        self.settings_button.clicked.connect(self.open_proxy_settings)
        button_layout.addWidget(self.settings_button)
        
        button_layout.addStretch()
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setDefault(True)
        button_layout.addWidget(self.ok_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # 自動閉じ機能（10秒後）
        self.auto_close_timer = QTimer()
        self.auto_close_timer.setSingleShot(True)
        self.auto_close_timer.timeout.connect(self.accept)
        self.auto_close_timer.start(10000)  # 10秒
        
        # 残り時間表示
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_remaining = 10
        self.countdown_timer.start(1000)  # 1秒間隔
        
    def _add_proxy_status_info(self, layout):
        """プロキシ状態情報を追加"""
        if not PYQT5_AVAILABLE:
            return
            
        info_label = QLabel()
        
        mode = self.proxy_config.get('mode', 'DIRECT')
        proxies = self.proxy_config.get('proxies', {})
        cert_config = self.proxy_config.get('cert', {})
        
        if mode == 'DIRECT':
            status_text = "🔗 直接接続"
            detail_text = "プロキシを使用せずに直接インターネットに接続します"
            ssl_status = "✅ SSL証明書検証: 有効" if cert_config.get('verify', True) else "⚠️ SSL証明書検証: 無効"
            
        elif mode == 'SYSTEM':
            http_proxy = proxies.get('http', 'なし')
            https_proxy = proxies.get('https', 'なし')
            
            if http_proxy != 'なし' or https_proxy != 'なし':
                status_text = "🌐 システムプロキシ使用"
                detail_text = f"HTTP: {http_proxy}\nHTTPS: {https_proxy}"
                ssl_status = "⚠️ SSL証明書検証: 無効（プロキシ環境対応）" if not cert_config.get('verify', True) else "✅ SSL証明書検証: 有効"
            else:
                status_text = "🔗 直接接続（システムプロキシなし）"
                detail_text = "システムプロキシが検出されませんでした"
                ssl_status = "✅ SSL証明書検証: 有効" if cert_config.get('verify', True) else "⚠️ SSL証明書検証: 無効"
                
        else:
            status_text = f"🔧 カスタム設定（{mode}）"
            detail_text = "カスタムプロキシ設定が適用されています"
            ssl_status = "✅ SSL証明書検証: 有効" if cert_config.get('verify', True) else "⚠️ SSL証明書検証: 無効"
        
        info_text = f"""
<b>{status_text}</b>

<b>詳細:</b>
{detail_text}

<b>セキュリティ設定:</b>
{ssl_status}
        """.strip()
        
        info_label.setText(info_text)
        info_label.setWordWrap(True)
        info_label.setStyleSheet("""
            QLabel {
                padding: 10px;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 5px;
            }
        """)
        layout.addWidget(info_label)
        
    def _add_settings_info(self, layout):
        """設定変更情報を追加"""
        if not PYQT5_AVAILABLE:
            return
            
        settings_info = QLabel("""
💡 <b>設定変更について:</b><br>
• 「アプリケーション設定」→「プロキシ設定」タブで変更可能<br>
• proxy_config_tool.py でコマンドライン設定も利用可能<br>
• 設定ファイル: config/network.yaml
        """)
        settings_info.setWordWrap(True)
        settings_info.setStyleSheet("color: #666; font-size: 10px; padding: 5px;")
        layout.addWidget(settings_info)
        
    def update_countdown(self):
        """カウントダウン表示更新"""
        if not PYQT5_AVAILABLE:
            return
            
        self.countdown_remaining -= 1
        if self.countdown_remaining > 0:
            self.ok_button.setText(f"OK ({self.countdown_remaining}秒で自動終了)")
        else:
            self.countdown_timer.stop()
            self.ok_button.setText("OK")
            
    def open_proxy_settings(self):
        """プロキシ設定を開く"""
        if not PYQT5_AVAILABLE:
            return
            
        try:
            # 親ウィンドウのプロキシ設定ダイアログを開く
            if self.parent():
                # 移行済みクラスを使用
                from classes.config.ui.proxy_settings_widget import ProxySettingsWidget
                proxy_widget = ProxySettingsWidget(self.parent())
                proxy_widget.exec_()
            else:
                # スタンドアロンでproxy_config_tool.pyを実行
                import subprocess
                import sys
                script_path = get_dynamic_file_path("proxy_config_tool.py")
                subprocess.Popen([sys.executable, script_path])
                
        except Exception as e:
            print(f"プロキシ設定開くエラー: {e}")
            
        self.accept()
        
    def accept(self):
        """ダイアログ終了時の処理"""
        if not PYQT5_AVAILABLE:
            return
            
        # 設定保存（今後表示しないオプション）
        if self.dont_show_again_checkbox.isChecked():
            self._save_notification_preference()
            
        super().accept()
        
    def _save_notification_preference(self):
        """通知設定の保存"""
        try:
            yaml_path = get_dynamic_file_path("config/network.yaml")
            
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                
            # 通知設定セクションを追加
            if 'ui' not in data:
                data['ui'] = {}
            data['ui']['show_startup_proxy_notification'] = False
            
            with open(yaml_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, default_flow_style=False, 
                             allow_unicode=True, sort_keys=False)
                             
        except Exception as e:
            print(f"通知設定保存エラー: {e}")

def should_show_startup_notification() -> bool:
    """起動時通知を表示すべきかどうかを判定"""
    try:
        yaml_path = get_dynamic_file_path("config/network.yaml")
        
        if not os.path.exists(yaml_path):
            return True  # 設定ファイルがない場合は表示
            
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            
        # デフォルトは表示する
        return data.get('ui', {}).get('show_startup_proxy_notification', True)
        
    except Exception as e:
        print(f"通知設定読み込みエラー: {e}")
        return True  # エラー時は表示

def show_proxy_startup_notification(proxy_config, parent=None):
    """プロキシ起動時通知を表示"""
    if not PYQT5_AVAILABLE:
        return
        
    if not should_show_startup_notification():
        return
        
    dialog = ProxyStartupNotificationDialog(proxy_config, parent)
    dialog.exec_()

if __name__ == "__main__":
    if PYQT5_AVAILABLE:
        from PyQt5.QtWidgets import QApplication
        
        app = QApplication(sys.argv)
        
        # テスト用のプロキシ設定
        test_config = {
            'mode': 'SYSTEM',
            'proxies': {
                'http': 'http://127.0.0.1:8888',
                'https': 'http://127.0.0.1:8888'
            },
            'cert': {
                'verify': False
            }
        }
        
        show_proxy_startup_notification(test_config)
        
        sys.exit(app.exec_())
    else:
        print("PyQt5が利用できません")
