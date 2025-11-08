from qt_compat.widgets import QWidget, QLabel
from qt_compat.core import Qt, QEvent
from qt_compat.gui import QPixmap
import os

class OverlayManager:
    """
    オーバーレイ（閲覧専用レイヤー）管理クラス
    """
    def __init__(self, parent, webview):
        self.parent = parent
        self.webview = webview
        self.overlay = None

    def show_overlay(self, watermark_text=None):
        from config.common import get_static_resource_path
        if self.overlay is not None:
            self.overlay.deleteLater()
        self.overlay = QWidget(self.parent)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        # --- 位置調整ここから ---
        webview_pos = self.webview.mapTo(self.parent, self.webview.rect().topLeft())
        webview_geom = self.webview.geometry()
        self.overlay.setGeometry(webview_pos.x(), webview_pos.y(), webview_geom.width(), webview_geom.height())
        # --- 位置調整ここまで ---
        if watermark_text is None:
            watermark_text = (
                "閲覧専用/操作不可\n"
                "このウインドウは自動処理に必要なため表示しています。\n"
                "操作すると正しく動作しない場合があります\n"
                "画像数が多いと時間がかかります\n"
            )
        label = QLabel(self.overlay)
        label.setText(watermark_text)
        label.setStyleSheet('color: rgba(0,0,0,1); font-size: 28px; font-weight: bold; background: transparent;')
        label.setAlignment(Qt.AlignCenter)
        label.setGeometry(self.overlay.rect())
        label.setWordWrap(True)
        label.show()
        image_paths = [
            get_static_resource_path("image/nanote_01.png"),
            get_static_resource_path("image/nanote_02.png"),
            get_static_resource_path("image/nanote_03.png"),
            get_static_resource_path("image/nanote_04.png"),
        ]
        # デバッグ: パスと存在確認
        for p in image_paths:
            print(f"[DEBUG] overlay image path: {p} exists: {os.path.exists(p)}")
        self._overlay_image_labels = []  # 画像ラベルを属性で保持
        positions = [
            (0, 0),
            (self.overlay.width() - 120, 0),
            (0, self.overlay.height() - 120),
            (self.overlay.width() - 120, self.overlay.height() - 120)
        ]
        for i, (x, y) in enumerate(positions):
            if i < len(image_paths):
                pixmap = QPixmap(image_paths[i])
                pixmap = pixmap.scaled(120, 120)
                image_label = QLabel(self.overlay)
                image_label.setPixmap(pixmap)
                image_label.setGeometry(x, y, 120, 120)
                image_label.setStyleSheet('background: transparent;')
                image_label.show()
                self._overlay_image_labels.append(image_label)
        self.overlay.setStyleSheet('background: rgba(168,207,118,0.5);')
        self.overlay.raise_()
        self.overlay.show()

    def hide_overlay(self):
        if self.overlay is not None:
            self.overlay.hide()

    def resize_overlay(self):
        if self.overlay is not None:
            # --- 位置調整ここから ---
            webview_pos = self.webview.mapTo(self.parent, self.webview.rect().topLeft())
            webview_geom = self.webview.geometry()
            self.overlay.setGeometry(webview_pos.x(), webview_pos.y(), webview_geom.width(), webview_geom.height())
            # --- 位置調整ここまで ---
            # 画像の位置も再配置
            if hasattr(self, '_overlay_image_labels'):
                positions = [
                    (0, 0),
                    (self.overlay.width() - 120, 0),
                    (0, self.overlay.height() - 120),
                    (self.overlay.width() - 120, self.overlay.height() - 120)
                ]
                for i, label in enumerate(self._overlay_image_labels):
                    if i < len(positions):
                        x, y = positions[i]
                        label.setGeometry(x, y, 120, 120)

    def event_filter(self, obj, event):
        if self.overlay is not None and obj == self.webview:
            if event.type() in [QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick, QEvent.MouseMove]:
                return True
        return False

