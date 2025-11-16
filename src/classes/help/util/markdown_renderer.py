"""
Markdownレンダリングユーティリティ - ARIM RDE Tool v2.1.3
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import QTextBrowser
    from qt_compat.core import Qt
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QTextBrowser: pass


def render_markdown_to_html(markdown_text: str) -> str:
    """MarkdownをHTMLに変換（簡易実装）"""
    
    if not markdown_text:
        return "<p>内容がありません</p>"
    
    html_parts = []
    html_parts.append('<style>')
    html_parts.append('''
        body { font-family: "Yu Gothic UI", "Meiryo UI", sans-serif; line-height: 1.6; }
        h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        h2 { color: #34495e; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; margin-top: 20px; }
        h3 { color: #7f8c8d; margin-top: 15px; }
        code { background-color: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: "Consolas", monospace; }
        pre { background-color: #f4f4f4; padding: 10px; border-radius: 5px; overflow-x: auto; }
        ul, ol { margin-left: 20px; }
        li { margin: 5px 0; }
        blockquote { border-left: 4px solid #3498db; padding-left: 15px; color: #7f8c8d; }
        a { color: #3498db; text-decoration: none; }
        a:hover { text-decoration: underline; }
    ''')
    html_parts.append('</style>')
    html_parts.append('<body>')
    
    lines = markdown_text.split('\n')
    in_code_block = False
    in_list = False
    
    for line in lines:
        # コードブロック
        if line.startswith('```'):
            if in_code_block:
                html_parts.append('</pre>')
                in_code_block = False
            else:
                html_parts.append('<pre><code>')
                in_code_block = True
            continue
        
        if in_code_block:
            html_parts.append(line.replace('<', '&lt;').replace('>', '&gt;'))
            continue
        
        # 見出し
        if line.startswith('### '):
            html_parts.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith('## '):
            html_parts.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('# '):
            html_parts.append(f'<h1>{line[2:]}</h1>')
        # リスト
        elif line.startswith('- ') or line.startswith('* '):
            if not in_list:
                html_parts.append('<ul>')
                in_list = True
            html_parts.append(f'<li>{line[2:]}</li>')
        elif line.startswith('1. ') or line.startswith('2. ') or line.startswith('3. '):
            content = line.split('. ', 1)[1] if '. ' in line else line
            if not in_list:
                html_parts.append('<ol>')
                in_list = True
            html_parts.append(f'<li>{content}</li>')
        # 引用
        elif line.startswith('> '):
            html_parts.append(f'<blockquote>{line[2:]}</blockquote>')
        # 空行
        elif not line.strip():
            if in_list:
                html_parts.append('</ul>' if html_parts[-2].startswith('<ul>') else '</ol>')
                in_list = False
            html_parts.append('<br>')
        # 通常のテキスト
        else:
            # インラインコード
            if '`' in line:
                line = line.replace('`', '<code>', 1).replace('`', '</code>', 1)
            html_parts.append(f'<p>{line}</p>')
    
    if in_list:
        html_parts.append('</ul>')
    if in_code_block:
        html_parts.append('</code></pre>')
    
    html_parts.append('</body>')
    
    return '\n'.join(html_parts)


def load_markdown_file(file_path: Path) -> str:
    """Markdownファイルを読み込む"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Markdownファイル読み込みエラー: {e}")
        return f"# エラー\n\nファイルの読み込みに失敗しました: {file_path}"


def create_markdown_viewer(markdown_text: str, parent=None) -> Optional[QTextBrowser]:
    """Markdown表示用のTextBrowserを作成"""
    if not PYQT5_AVAILABLE:
        return None
    
    viewer = QTextBrowser(parent)
    viewer.setOpenExternalLinks(True)
    
    # HTMLに変換して表示
    html = render_markdown_to_html(markdown_text)
    viewer.setHtml(html)
    
    return viewer
