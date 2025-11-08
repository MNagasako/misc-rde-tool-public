import time
from PyQt5.QtWidgets import QWidget, QPushButton

def wait_for_form_and_click_button(window, form_object_name, button_object_name, timeout=30, interval=0.5, test_mode=False):
    """
    テストモード時のみ、フォームが表示されるまで待機し、表示されたらボタンを自動クリックする。
    通常動作には影響しない。
    """
    if not test_mode:
        return  # 通常動作時は何もしない

    start = time.time()
    while time.time() - start < timeout:
        form = window.findChild(QWidget, form_object_name)
        button = window.findChild(QPushButton, button_object_name)
        if form and form.isVisible() and button and button.isEnabled():
            button.click()
            print(f"[TEST] ボタン({button_object_name})を自動クリックしました")
            return True
        time.sleep(interval)
    print(f"[TEST] フォーム({form_object_name})が{timeout}秒以内に表示されませんでした")
    return False
