"""
データ取得2機能 - ファイルフィルタ設定
ファイルタイプ、メディアタイプ、拡張子、サイズによるフィルタ設定
"""

# 既存データ分析に基づく設定値

# ファイルタイプ選択肢（実データから）
FILE_TYPES = [
    "MAIN_IMAGE",
    "STRUCTURED", 
    "NONSHARED_RAW",
    "RAW",
    "META",
    "ATTACHEMENT",
    "THUMBNAIL"
]



# メディアタイプ選択肢（実データから）
MEDIA_TYPES = [
    "image/png",
    "image/tiff", 
    "text/plain",
    "application/octet-stream",
    "image/jpeg"
]

# 拡張子選択肢（実データから）
FILE_EXTENSIONS = [
    "png",
    "tif",
    "dm4", 
    "csv",
    "json",
    "jpeg"
]

# ファイルサイズ範囲設定
FILE_SIZE_RANGES = {
    "tiny": (0, 1024),           # 1KB未満
    "small": (1024, 102400),     # 1KB-100KB
    "medium": (102400, 10485760), # 100KB-10MB
    "large": (10485760, 104857600), # 10MB-100MB
    "huge": (104857600, float('inf')) # 100MB以上
}

# デフォルトフィルタ設定
DEFAULT_FILTER = {
    "file_types": ["MAIN_IMAGE"],  # 従来通りMAIN_IMAGEのみ
    "media_types": [],             # 制限なし
    "extensions": [],              # 制限なし
    "size_min": 0,                 # 最小サイズ（bytes）
    "size_max": 0,                 # 最大サイズ（0=制限なし）
    "filename_pattern": "",        # ファイル名パターン（*ワイルドカード対応）
    "max_download_count": 0        # ダウンロード上限（0=制限なし）
}

# フィルタUI表示ラベル
FILTER_LABELS = {
    "file_types": "ファイルタイプ",
    "media_types": "メディアタイプ", 
    "extensions": "拡張子",
    "size_range": "ファイルサイズ",
    "filename_pattern": "ファイル名パターン",
    "max_download_count": "ダウンロード上限"
}

def get_default_filter():
    """デフォルトフィルタ設定を取得"""
    return DEFAULT_FILTER.copy()