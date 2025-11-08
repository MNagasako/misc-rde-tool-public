
from qt_compat.widgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QLineEdit, QPushButton, QMessageBox
from qt_compat.core import Qt
import os
import json

class PasswordAuthDialog(QDialog):
    """パスワード認証ダイアログ"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RDE Dataset Creation GUI - 認証")
        self.setModal(True)
        self.setFixedSize(400, 200)
        self.correct_password = "$admin"  # デフォルトパスワード
        self.attempt_count = 0
        self.max_attempts = 3
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        title_label = QLabel("RDE Dataset Creation GUI")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)
        info_label = QLabel("この機能にアクセスするには認証が必要です。")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("margin: 10px;")
        layout.addWidget(info_label)
        password_layout = QHBoxLayout()
        password_layout.addWidget(QLabel("パスワード:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("パスワードを入力してください")
        self.password_input.returnPressed.connect(self.authenticate)
        password_layout.addWidget(self.password_input)
        layout.addLayout(password_layout)
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: red; margin: 5px;")
        self.warning_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.warning_label)
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("認証")
        self.ok_button.clicked.connect(self.authenticate)
        self.ok_button.setDefault(True)
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.password_input.setFocus()

    def authenticate(self):
        entered_password = self.password_input.text()
        if entered_password == self.correct_password:
            self.accept()
        else:
            self.attempt_count += 1
            remaining_attempts = self.max_attempts - self.attempt_count
            if remaining_attempts > 0:
                self.warning_label.setText(f"パスワードが間違っています。残り{remaining_attempts}回")
                self.password_input.clear()
                self.password_input.setFocus()
            else:
                QMessageBox.critical(self, "認証失敗", f"認証に{self.max_attempts}回失敗しました。アプリケーションを終了します。")
                self.reject()

    def load_password_config(self):
        from config.common import get_dynamic_file_path
        config_file = get_dynamic_file_path('tools/config/auth_config.json')
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.correct_password = config.get('gui_password', self.correct_password)
                    self.max_attempts = config.get('max_attempts', self.max_attempts)
        except Exception as e:
            print(f"認証設定ファイルの読み込みに失敗: {e}")
