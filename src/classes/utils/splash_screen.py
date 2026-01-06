import os
import sys
from config.common import get_static_resource_path, REVISION

import logging

# ロガー設定
logger = logging.getLogger(__name__)

import random

from classes.managers.app_config_manager import get_config_manager


def _env_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_splash_enabled() -> bool:
    """スプラッシュ表示の有効/無効を判定。

    既定は有効。
    - `RDE_DISABLE_SPLASH_SCREEN` が truthy なら常に無効
    - `RDE_ENABLE_SPLASH_SCREEN` が truthy なら常に有効
    - それ以外は config `app.enable_splash_screen` を参照
    """
    try:
        if _env_truthy(os.environ.get("RDE_DISABLE_SPLASH_SCREEN")):
            return False
        if _env_truthy(os.environ.get("RDE_ENABLE_SPLASH_SCREEN")):
            return True
    except Exception:
        # env 参照に失敗しても既定有効
        return True

    try:
        cfg = get_config_manager()
        return bool(cfg.get("app.enable_splash_screen", True))
    except Exception:
        return True

def show_splash_screen():
    # 判定側で無効の場合は何もしない
    if not is_splash_enabled():
        return

    # tkinter/Pillow は必要時のみ import する（環境差異に強くする）
    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except Exception as e:
        logger.warning("スプラッシュ画面の依存関係 import に失敗: %s", e)
        return

    try:
        from classes.theme import ThemeKey, get_color

        text_color = get_color(ThemeKey.TEXT_PRIMARY)
        accent_color = get_color(ThemeKey.TEXT_LINK)
        muted_color = get_color(ThemeKey.TEXT_MUTED)

        root = tk.Tk()
        root.title("スプラッシュ画面")
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = 400
        window_height = 400
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        root.overrideredirect(True)
        root.lift()
        root.focus_force()
        # キャンバス
        canvas = tk.Canvas(root, width=250, height=250)
        canvas.pack(fill="both", expand=True)
        # 画像表示（失敗時はテキストのみ）
        try:
            images = [
                get_static_resource_path("image/nanote_01.png"),         
                get_static_resource_path("image/nanote_02.png"),
                get_static_resource_path("image/nanote_03.png"),
                get_static_resource_path("image/nanote_04.png"),        
            ]
            selected_images = random.sample(images, 2)
            image1 = Image.open(selected_images[0])
            image1.thumbnail((200, 200), Image.Resampling.LANCZOS)
            bg_image1 = ImageTk.PhotoImage(image1)
            image2 = Image.open(selected_images[1])
            image2.thumbnail((200,200), Image.Resampling.LANCZOS)
            bg_image2 = ImageTk.PhotoImage(image2)
            canvas.create_image(100, 155, image=bg_image1, anchor="center")
            canvas.create_image(300, 155, image=bg_image2, anchor="center")
            # アイコン
            try:
                icon_path = get_static_resource_path("image/icon/icon1.ico")
                icon_image = Image.open(icon_path)
                icon_image.thumbnail((80, 80), Image.Resampling.LANCZOS)
                tk_icon_image = ImageTk.PhotoImage(icon_image)
                canvas.create_image(200, 210, image=tk_icon_image, anchor="center")
            except Exception:
                pass
        except Exception:
            pass
        # テキストは必ず表示
        canvas.create_text(200, 280, text="ARIMデータカタログ", fill=text_color, font=("Arial", 12, "bold"))
        canvas.create_text(200, 300, text="作成支援ツール（仮）", fill=text_color, font=("Arial", 12, "bold"))
        canvas.create_text(200, 320, text=f"Version {REVISION}", fill=accent_color, font=("Arial", 10, "bold"))
        canvas.create_text(200, 340, text="GitHub: MNagasako/misc-rde-tool-public", fill=muted_color, font=("Arial", 10))
        root.after(2000, root.destroy)
        root.mainloop()
    except Exception as e:
        logger.warning("スプラッシュ画面の表示に失敗: %s", e)
        # 失敗してもPyQt5起動を妨げない

if __name__ == "__main__":
    show_splash_screen()

