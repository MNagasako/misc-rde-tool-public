"""
カスタムQWebEnginePageクラス - JavaScriptコンソールメッセージの表示

PyQt5/PySide6互換レイヤー
"""

from .webengine import QtWebEngineCore
import logging

logger = logging.getLogger(__name__)


class WebEnginePageWithConsole(QtWebEngineCore.QWebEnginePage):
    """
    JavaScriptコンソールメッセージをPythonロガーに転送するカスタムPage
    
    PySide6のQWebEnginePageでは、javaScriptConsoleMessageメソッドを
    オーバーライドすることで、ブラウザ内のconsole.log()出力を取得できます。
    """
    
    def __init__(self, profile, parent=None):
        """
        初期化
        
        Args:
            profile: QWebEngineProfile インスタンス
            parent: 親ウィジェット
        """
        super().__init__(profile, parent)
        logger.info("[WEBENGINE] WebEnginePageWithConsole初期化完了")
    
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        """
        JavaScriptコンソールメッセージのハンドラ
        
        Args:
            level: メッセージレベル（InfoMessageLevel, WarningMessageLevel, ErrorMessageLevel）
            message: コンソールメッセージ
            lineNumber: ソース行番号
            sourceID: ソースID（通常はURL）
        """
        # PySide6: JavaScriptConsoleMessageLevelは整数値として渡される
        # 0: InfoMessageLevel
        # 1: WarningMessageLevel
        # 2: ErrorMessageLevel
        
        # すべてのメッセージをINFOレベルで出力（デバッグ用）
        logger.info(f"[JS-Console] level={level}, msg={message} (line: {lineNumber})")
        
        # メッセージレベルに応じてログ出力
        try:
            if level == 0:  # InfoMessageLevel
                logger.info(f"[JS-Console-INFO] {message}")
            elif level == 1:  # WarningMessageLevel
                logger.warning(f"[JS-Console-WARN] {message}")
            elif level == 2:  # ErrorMessageLevel
                logger.error(f"[JS-Console-ERROR] {message}")
            else:
                logger.debug(f"[JS-Console-UNKNOWN] level={level}, {message}")
        except Exception as e:
            logger.error(f"[JS-Console] ログ出力エラー: {e}, level={level}, message={message}")
