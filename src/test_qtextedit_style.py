"""
QTextEdit stylesheet test script
"""
import sys
sys.path.insert(0, 'src')

from classes.theme import get_color, ThemeKey, ThemeManager

# Initialize theme
theme_manager = ThemeManager.instance()

# Test the problematic stylesheet
colors = ["green", "red", "orange", None]

for color in colors:
    print(f"\n=== Testing color: {color} ===")
    
    if color == "green":
        style = f"QTextEdit {{ font-family: 'Consolas'; font-size: 9pt; border: 2px solid green; background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; color: {get_color(ThemeKey.INPUT_TEXT)}; }}"
    elif color == "red":
        style = f"QTextEdit {{ font-family: 'Consolas'; font-size: 9pt; border: 2px solid red; background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; color: {get_color(ThemeKey.INPUT_TEXT)}; }}"
    elif color == "orange":
        style = f"QTextEdit {{ font-family: 'Consolas'; font-size: 9pt; border: 2px solid orange; background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; color: {get_color(ThemeKey.INPUT_TEXT)}; }}"
    else:
        style = f"QTextEdit {{ font-family: 'Consolas'; font-size: 9pt; background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; color: {get_color(ThemeKey.INPUT_TEXT)}; }}"
    
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
