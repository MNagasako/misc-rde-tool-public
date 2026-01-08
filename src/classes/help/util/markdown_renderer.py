"""Markdownレンダリングユーティリティ - ARIM RDE Tool v2.4.12"""

import logging
import os
from pathlib import Path
from typing import Optional

from config.common import get_base_dir, get_static_resource_path

from classes.theme import ThemeKey, get_color

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import QTextBrowser
    from qt_compat.core import QUrl
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
        body { 
            font-family: "Yu Gothic UI", "Meiryo UI", sans-serif; 
            line-height: 1.5; 
            margin: 0;
            padding: 0;
            font-size: 11pt;
            background: transparent;
            color: ''' + get_color(ThemeKey.TEXT_PRIMARY) + ''';
        }
        h1 { 
            color: ''' + get_color(ThemeKey.MARKDOWN_H1_TEXT) + '''; 
            border-bottom: 2px solid ''' + get_color(ThemeKey.MARKDOWN_H1_BORDER) + '''; 
            padding-bottom: 8px;
            margin-top: 16px;
            margin-bottom: 12px;
            font-size: 16pt;
        }
        h2 { 
            color: ''' + get_color(ThemeKey.MARKDOWN_H2_TEXT) + '''; 
            border-bottom: 1px solid ''' + get_color(ThemeKey.MARKDOWN_H2_BORDER) + '''; 
            padding-bottom: 4px; 
            margin-top: 14px;
            margin-bottom: 10px;
            font-size: 13pt;
        }
        h3 { 
            color: ''' + get_color(ThemeKey.MARKDOWN_H3_TEXT) + '''; 
            margin-top: 12px;
            margin-bottom: 8px;
            font-size: 11.5pt;
        }
        p {
            margin-top: 6px;
            margin-bottom: 6px;
        }
        code { 
            background-color: ''' + get_color(ThemeKey.MARKDOWN_CODE_BACKGROUND) + '''; 
            padding: 1px 4px; 
            border-radius: 3px; 
            font-family: "Consolas", monospace;
            font-size: 10pt;
        }
        pre { 
            background-color: ''' + get_color(ThemeKey.MARKDOWN_CODE_BACKGROUND) + '''; 
            padding: 8px; 
            border-radius: 4px; 
            overflow-x: auto;
            margin-top: 8px;
            margin-bottom: 8px;
            line-height: 1.4;
        }
        ul, ol { 
            margin-left: 20px;
            margin-top: 6px;
            margin-bottom: 6px;
            padding-left: 0;
        }
        li { 
            margin: 3px 0;
        }
        blockquote { 
            border-left: 3px solid ''' + get_color(ThemeKey.MARKDOWN_BLOCKQUOTE_BORDER) + '''; 
            padding-left: 12px; 
            color: ''' + get_color(ThemeKey.MARKDOWN_BLOCKQUOTE_TEXT) + ''';
            margin-top: 8px;
            margin-bottom: 8px;
            margin-left: 4px;
        }
        a { 
            color: ''' + get_color(ThemeKey.MARKDOWN_LINK) + '''; 
            text-decoration: none; 
        }
        a:hover { 
            text-decoration: underline; 
        }
        br {
            line-height: 0.5;
        }
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


def set_markdown_document(
    text_browser: QTextBrowser,
    markdown_text: str,
    base_path: Optional[str] = None,
) -> None:
    """Apply markdown text directly to a QTextBrowser with optional base path."""

    if not PYQT5_AVAILABLE:
        return

    document = text_browser.document()
    if base_path:
        base_dir = base_path if os.path.isdir(base_path) else os.path.dirname(base_path)
        if base_dir:
            document.setBaseUrl(QUrl.fromLocalFile(base_dir))

    safe_text = markdown_text if markdown_text.strip() else "内容がありません"
    document.setMarkdown(safe_text)


def load_markdown_file(file_path: Path) -> str:
    """Markdownファイルを読み込む"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Markdownファイル読み込みエラー: {e}")
        return f"# エラー\n\nファイルの読み込みに失敗しました: {file_path}"


def load_help_markdown(filename: str) -> tuple[str, Optional[str]]:
    """Load help markdown from the bundled resources (with legacy fallback)."""

    candidates: list[str] = []
    try:
        candidates.append(get_static_resource_path(os.path.join('resources', 'docs', 'help', filename)))
    except Exception as exc:  # pragma: no cover - diagnostic logging only
        logger.debug("静的リソースパスの解決に失敗: %s", exc)

    legacy_path = os.path.join(get_base_dir(), 'docs', 'help', filename)
    candidates.append(legacy_path)

    for path in candidates:
        if path and os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as handle:
                return handle.read(), os.path.dirname(path)

    raise FileNotFoundError(f"help markdown not found: {filename}")


def create_markdown_viewer(markdown_text: str, parent=None, base_path: Optional[str] = None) -> Optional[QTextBrowser]:
    """Markdown表示用のTextBrowserを作成"""
    if not PYQT5_AVAILABLE:
        return None
    
    viewer = QTextBrowser(parent)
    viewer.setOpenExternalLinks(True)
    set_markdown_document(viewer, markdown_text, base_path)
    
    return viewer
