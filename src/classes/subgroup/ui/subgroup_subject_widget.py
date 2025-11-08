"""
サブグループ課題入力ウィジェット
課題番号と課題名のペアを追加・編集・削除できるUIコンポーネント
"""
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView
)
from qt_compat.core import Qt, Signal
from qt_compat.gui import QFont


class SubjectEntryWidget(QWidget):
    """課題入力専用ウィジェット"""
    
    # データ変更時のシグナル
    dataChanged = Signal()
    
    def __init__(self, initial_subjects=None):
        """
        Args:
            initial_subjects (list): 初期課題データ [{"grantNumber": "", "title": ""}, ...]
        """
        super().__init__()
        self.subjects_data = initial_subjects or []
        self.setup_ui()
        self.populate_table()
    
    def setup_ui(self):
        """UIセットアップ"""
        layout = QVBoxLayout()
        
        # ヘッダー部分
        header_layout = QHBoxLayout()
        #header_label = QLabel("課題一覧")
        #header_label.setFont(QFont("", 10, QFont.Bold))
        #header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # 追加ボタン
        self.add_button = QPushButton("+ 課題追加")
        self.add_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.add_button.clicked.connect(self.add_subject)
        #header_layout.addWidget(self.add_button)
        
        #layout.addLayout(header_layout)
        
        # テーブル部分
        self.table = QTableWidget()
        self.table.setColumnCount(3)  # 課題番号、課題名、削除ボタン
        self.table.setHorizontalHeaderLabels(["課題番号 *", "課題名", ""])
        
        # テーブル設定
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(120)
        self.table.setMaximumHeight(160)
        
        # 列幅設定
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)  # 課題番号
        header.setSectionResizeMode(1, QHeaderView.Stretch)      # 課題名
        header.setSectionResizeMode(2, QHeaderView.Fixed)        # 削除ボタン
        self.table.setColumnWidth(0, 180)  # 課題番号列
        self.table.setColumnWidth(2, 60)   # 削除ボタン列
        
        layout.addWidget(self.table)
        
        # 入力フォーム部分
        form_layout = QHBoxLayout()
        
        # 課題番号入力
        form_layout.addWidget(QLabel("課題番号:"))
        self.grant_number_edit = QLineEdit()
        self.grant_number_edit.setPlaceholderText("例: JPMXP1225TU9999-TEST")
        self.grant_number_edit.setMaximumWidth(200)
        form_layout.addWidget(self.grant_number_edit)
        
        # 課題名入力
        form_layout.addWidget(QLabel("課題名:"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("例: 研究課題名（省略可）")
        form_layout.addWidget(self.title_edit)
        
        # 追加ボタン
        self.add_from_form_button = QPushButton("追加")
        self.add_from_form_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.add_from_form_button.clicked.connect(self.add_from_form)
        form_layout.addWidget(self.add_from_form_button)
        
        layout.addLayout(form_layout)
        
        # Enterキーでの追加対応
        self.grant_number_edit.returnPressed.connect(self.add_from_form)
        self.title_edit.returnPressed.connect(self.add_from_form)
        
        self.setLayout(layout)
    
    def populate_table(self):
        """テーブルにデータを設定"""
        self.table.setRowCount(len(self.subjects_data))
        
        for row, subject in enumerate(self.subjects_data):
            # 課題番号
            grant_number_item = QTableWidgetItem(subject.get("grantNumber", ""))
            grant_number_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable)
            self.table.setItem(row, 0, grant_number_item)
            
            # 課題名
            title_item = QTableWidgetItem(subject.get("title", ""))
            title_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable)
            self.table.setItem(row, 1, title_item)
            
            # 削除ボタン
            delete_button = QPushButton("削除")
            delete_button.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    border: none;
                    padding: 2px 8px;
                    border-radius: 2px;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            delete_button.clicked.connect(lambda checked, r=row: self.delete_subject(r))
            self.table.setCellWidget(row, 2, delete_button)
        
        # セル編集完了時のイベント接続
        self.table.itemChanged.connect(self.on_item_changed)
    
    def add_subject(self):
        """空の課題を追加"""
        self.subjects_data.append({"grantNumber": "", "title": ""})
        self.populate_table()
        self.dataChanged.emit()
        
        # 新しく追加された行の課題番号セルにフォーカス
        new_row = len(self.subjects_data) - 1
        self.table.setCurrentCell(new_row, 0)
        self.table.editItem(self.table.item(new_row, 0))
    
    def add_from_form(self):
        """フォームから課題を追加"""
        grant_number = self.grant_number_edit.text().strip()
        title = self.title_edit.text().strip()
        
        if not grant_number:
            QMessageBox.warning(self, "入力エラー", "課題番号を入力してください。")
            self.grant_number_edit.setFocus()
            return
        
        # 重複チェック
        for subject in self.subjects_data:
            if subject.get("grantNumber") == grant_number:
                QMessageBox.warning(self, "重複エラー", f"課題番号 '{grant_number}' は既に存在します。")
                self.grant_number_edit.setFocus()
                return
        
        # 課題名が空の場合は課題番号を使用
        if not title:
            title = grant_number
        
        self.subjects_data.append({"grantNumber": grant_number, "title": title})
        self.populate_table()
        self.dataChanged.emit()
        
        # フォームクリア
        self.grant_number_edit.clear()
        self.title_edit.clear()
        self.grant_number_edit.setFocus()
    
    def delete_subject(self, row):
        """指定行の課題を削除"""
        if 0 <= row < len(self.subjects_data):
            subject = self.subjects_data[row]
            grant_number = subject.get("grantNumber", "")
            
            reply = QMessageBox.question(
                self, 
                "削除確認", 
                f"課題番号 '{grant_number}' を削除しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                del self.subjects_data[row]
                self.populate_table()
                self.dataChanged.emit()
    
    def on_item_changed(self, item):
        """テーブルセル編集完了時"""
        row = item.row()
        col = item.column()
        
        if row < len(self.subjects_data):
            if col == 0:  # 課題番号
                old_grant_number = self.subjects_data[row].get("grantNumber", "")
                new_grant_number = item.text().strip()
                
                # 重複チェック（自分以外）
                for i, subject in enumerate(self.subjects_data):
                    if i != row and subject.get("grantNumber") == new_grant_number:
                        QMessageBox.warning(self, "重複エラー", f"課題番号 '{new_grant_number}' は既に存在します。")
                        item.setText(old_grant_number)  # 元に戻す
                        return
                
                self.subjects_data[row]["grantNumber"] = new_grant_number
                
                # 課題名が空または古い課題番号と同じ場合、新しい課題番号を設定
                current_title = self.subjects_data[row].get("title", "")
                if not current_title or current_title == old_grant_number:
                    self.subjects_data[row]["title"] = new_grant_number
                    # テーブル更新
                    title_item = self.table.item(row, 1)
                    if title_item:
                        title_item.setText(new_grant_number)
                
            elif col == 1:  # 課題名
                self.subjects_data[row]["title"] = item.text().strip()
            
            self.dataChanged.emit()
    
    def get_subjects_data(self):
        """課題データを取得"""
        # 空の課題番号を除外
        return [
            subject for subject in self.subjects_data 
            if subject.get("grantNumber", "").strip()
        ]
    
    def set_subjects_data(self, subjects):
        """課題データを設定"""
        self.subjects_data = subjects or []
        self.populate_table()
        self.dataChanged.emit()
    
    def validate_subjects(self):
        """課題データのバリデーション"""
        valid_subjects = []
        errors = []
        
        for i, subject in enumerate(self.subjects_data):
            grant_number = subject.get("grantNumber", "").strip()
            title = subject.get("title", "").strip()
            
            if not grant_number:
                continue  # 空の課題番号はスキップ
            
            # 課題番号の形式チェック（半角英数字とハイフンのみ）
            if not all(c.isalnum() or c in '-_' for c in grant_number):
                errors.append(f"行{i+1}: 課題番号に無効な文字が含まれています: {grant_number}")
                continue
            
            # 課題名が空の場合は課題番号を使用
            if not title:
                title = grant_number
            
            valid_subjects.append({"grantNumber": grant_number, "title": title})
        
        return valid_subjects, errors
    
    def clear_all(self):
        """全ての課題をクリア"""
        reply = QMessageBox.question(
            self, 
            "クリア確認", 
            "全ての課題をクリアしますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.subjects_data.clear()
            self.populate_table()
            self.dataChanged.emit()


def parse_subjects_from_text(text):
    """
    従来のテキスト形式から課題データに変換
    
    Args:
        text (str): "課題番号:課題名,課題番号:課題名,..." 形式のテキスト
        
    Returns:
        list: [{"grantNumber": "", "title": ""}, ...] 形式の課題リスト
    """
    subjects = []
    if not text.strip():
        return subjects
    
    parts = [p.strip() for p in text.split(',') if p.strip()]
    for part in parts:
        if ':' in part:
            grant_number, title = part.split(':', 1)
            grant_number = grant_number.strip()
            title = title.strip()
            
            if grant_number:
                subjects.append({
                    "grantNumber": grant_number,
                    "title": title if title else grant_number
                })
        else:
            # コロンがない場合は課題番号のみとして扱う
            grant_number = part.strip()
            if grant_number:
                subjects.append({
                    "grantNumber": grant_number,
                    "title": grant_number
                })
    
    return subjects


def subjects_to_text(subjects):
    """
    課題データを従来のテキスト形式に変換
    
    Args:
        subjects (list): [{"grantNumber": "", "title": ""}, ...] 形式の課題リスト
        
    Returns:
        str: "課題番号:課題名,課題番号:課題名,..." 形式のテキスト
    """
    if not subjects:
        return ""
    
    parts = []
    for subject in subjects:
        grant_number = subject.get("grantNumber", "").strip()
        title = subject.get("title", "").strip()
        
        if grant_number:
            if title and title != grant_number:
                parts.append(f"{grant_number}:{title}")
            else:
                parts.append(grant_number)
    
    return ",".join(parts)
