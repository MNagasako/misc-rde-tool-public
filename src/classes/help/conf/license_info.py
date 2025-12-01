"""
ライセンス情報定義 - ARIM RDE Tool v2.1.12
"""

# アプリケーション情報
APP_NAME = "ARIM RDE Tool"
APP_VERSION = "v2.1.12"
APP_DESCRIPTION = "ARIM事業 RDEシステム/データポータル の 操作支援ツール"
APP_AUTHOR = "MNagasako"
APP_COPYRIGHT = "Copyright © 2024-2025 MNagasako"

# ライセンス情報
LICENSE_TEXT = """
MIT License

Copyright (c) 2024-2025 MNagasako

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# サードパーティライセンス情報
THIRD_PARTY_LICENSES = """
## サードパーティライブラリ

本アプリケーションは以下のオープンソースライブラリを使用しています：

### PySide6 / PyQt5
- ライセンス: LGPL v3
- 詳細: https://www.qt.io/licensing/

### requests
- ライセンス: Apache License 2.0
- 詳細: https://requests.readthedocs.io/

### pandas
- ライセンス: BSD 3-Clause License
- 詳細: https://pandas.pydata.org/

### BeautifulSoup4
- ライセンス: MIT License
- 詳細: https://www.crummy.com/software/BeautifulSoup/

### その他
詳細なライセンス情報は LICENSES.md および THIRD_PARTY_NOTICES/ ディレクトリをご参照ください。
"""

def get_full_license_text():
    """完全なライセンステキストを取得"""
    return f"{LICENSE_TEXT}\n\n{THIRD_PARTY_LICENSES}"
