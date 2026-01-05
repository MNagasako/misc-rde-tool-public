"""
QTextEdit stylesheet test script
"""
import sys

from classes.theme import get_color, ThemeKey, ThemeManager

# Initialize theme
theme_manager = ThemeManager.instance()

# Test the problematic stylesheet
border_keys = [ThemeKey.TEXT_SUCCESS, ThemeKey.TEXT_ERROR, ThemeKey.TEXT_WARNING, None]

for border_key in border_keys:
    print(f"\n=== Testing border key: {border_key} ===")
    
    if border_key is None:
        style = (
            f"QTextEdit {{ font-family: 'Consolas'; font-size: 9pt; "
            f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; color: {get_color(ThemeKey.INPUT_TEXT)}; }}"
        )
    else:
        style = (
            f"QTextEdit {{ font-family: 'Consolas'; font-size: 9pt; border: 1px solid {get_color(border_key)}; "
            f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; color: {get_color(ThemeKey.INPUT_TEXT)}; }}"
        )
    
    print(f"Style length: {len(style)}")
    print(f"Style: {style}")
    
    # Check for syntax issues
    if style.count('{') != style.count('}'):
        print("ERROR: Mismatched braces!")
    else:
        print("OK: Braces matched")
    
    # Test with QTextEdit
    try:
        from qt_compat.widgets import QApplication, QTextEdit
        app = QApplication.instance() or QApplication(sys.argv)
        
        widget = QTextEdit()
        widget.setStyleSheet(style)
        print("SUCCESS: Stylesheet applied without error")
        
    except Exception as e:
        print(f"ERROR: {e}")

print("\n=== Test complete ===")
