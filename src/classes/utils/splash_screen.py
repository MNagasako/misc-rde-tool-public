import os
import sys
from config.common import get_static_resource_path, REVISION

from PIL import Image, ImageTk
import tkinter as tk
import time
import random

def show_splash_screen():
    try:
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
        canvas.create_text(200, 280, text="ARIMデータカタログ", fill="black", font=("Arial", 12, "bold"))
        canvas.create_text(200, 300, text="作成支援ツール（仮）", fill="black", font=("Arial", 12, "bold"))
        canvas.create_text(200, 320, text=f"Version {REVISION}", fill="blue", font=("Arial", 10, "bold"))
        canvas.create_text(200, 340, text="GitHub: MNagasako/misc-rde-tool-public", fill="black", font=("Arial", 10))
        root.after(2000, root.destroy)
        root.mainloop()
    except Exception as e:
        print(f"[WARN] スプラッシュ画面の表示に失敗: {e}")
        # 失敗してもPyQt5起動を妨げない

if __name__ == "__main__":
    show_splash_screen()

