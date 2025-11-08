import time
from qt_compat.widgets import QWidget, QPushButton
from qt_compat.core import QTimer

def wait_for_form_and_click_button(window, form_object_name, button_object_name, timeout=10, interval=0.5, test_mode=False):
    """
    テストモード時のみ、フォームが表示されるまで非同期で待機し、表示されたらボタンを自動クリックする。
    通常動作には影響しない。
    """
    if not test_mode:
        return  # 通常動作時は何もしない

    elapsed = {'time': 0}
    interval_ms = int(interval * 1000)
    timeout_ms = int(timeout * 1000)

    def poll():
        form = window.findChild(QWidget, form_object_name)
        button = window.findChild(QPushButton, button_object_name)
        if form and form.isVisible() and button and button.isEnabled():
            button.click()
            print(f"[TEST] ボタン({button_object_name})を自動クリックしました")
            return  # 成功したら終了
        elapsed['time'] += interval_ms
        if elapsed['time'] < timeout_ms:
            QTimer.singleShot(interval_ms, poll)
        else:
            print(f"[TEST] フォーム({form_object_name})が{timeout}秒以内に表示されませんでした")

    QTimer.singleShot(interval_ms, poll)

def sanitize_path_name(name):
    """
    ファイル名やディレクトリ名に使えない文字を安全な文字に置換する
    """
    import re
    return re.sub(r'[\\/:*?"<>|]', '_', name)
