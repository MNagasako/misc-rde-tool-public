# データセット開設実行ボタンのロジック（ポップアップ表示のみ）
# ファイル名: dataset_create_logic.py

from PyQt5.QtWidgets import QMessageBox

def show_dataset_create_popup(parent=None):
    """
    データセット開設実行ボタン押下時にポップアップを表示するロジック
    """
    QMessageBox.information(
        parent,
        "データセット開設",
        "データセット開設リクエストが実行されました（ダミー表示）"
    )
