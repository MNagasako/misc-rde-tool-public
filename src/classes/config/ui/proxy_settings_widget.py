#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
プロキシ設定ウィジェット v1.17.2
ネットワークプロキシ設定の表示・編集・切り替え機能を提供

主要機能:
- 現在のプロキシ状態表示
- プロキシモード切り替え（DIRECT/SYSTEM/HTTP）
- プリセット設定の適用
- 接続テスト機能
- システムプロキシ自動検出

移行済み: src/widgets → src/classes/config/ui
"""

import os
import sys
import logging
from typing import Dict, Any, Optional

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QComboBox, QLineEdit, QPushButton, QTextEdit,
        QGroupBox, QRadioButton, QButtonGroup, QProgressBar,
        QMessageBox, QFrame, QScrollArea, QCheckBox, QInputDialog
    )
    from qt_compat.core import QTimer, QThread, Signal, Qt
    from qt_compat.gui import QFont, QPalette
    from classes.theme import get_color, ThemeKey
    PYQT5_AVAILABLE = True
except ImportError:
    # PyQt5が利用できない場合のフォールバック
    PYQT5_AVAILABLE = False
    
    # ダミークラス
    class QWidget: pass
    class QThread: pass
    def Signal(*args): return lambda: None

# ログ設定
logger = logging.getLogger(__name__)

class ProxyTestWorker(QThread):
    """プロキシ接続テストのワーカースレッド（4パターンの接続性評価）"""
    test_completed = Signal(dict)  # テスト結果辞書
    progress_updated = Signal(str, int)  # メッセージ, 進捗率
    
    def __init__(self, proxy_config: Dict[str, Any], header_pattern: str = 'python_default', custom_headers: Dict[str, str] = None):
        super().__init__()
        self.proxy_config = proxy_config
        self.timeout = 10  # 各テストのタイムアウト（秒）
        self._cancelled = False
        self.test_url = "https://rde.nims.go.jp/"
        self.header_pattern = header_pattern
        self.custom_headers = custom_headers or {}
        
        
    def run(self):
        """接続テスト実行（4パターンの接続性評価）
        
        1. 直接接続（プロキシなし）
        2. プロキシ経由（CA証明書なし・truststore不使用・SSL検証あり）
        3. プロキシ経由（CA証明書なし・truststore不使用・SSL検証なし）
        4. プロキシ経由（CA証明書あり・truststore使用・SSL検証あり）
        """
        if not PYQT5_AVAILABLE:
            return
        
        import time
        
        results = {
            'pattern1_direct': {'success': False, 'message': '', 'details': '', 'time': 0},
            'pattern2_proxy_no_ca_verify_on': {'success': False, 'message': '', 'details': '', 'time': 0},
            'pattern3_proxy_no_ca_verify_off': {'success': False, 'message': '', 'details': '', 'time': 0},
            'pattern4_proxy_with_ca': {'success': False, 'message': '', 'details': '', 'time': 0},
            'overall_success': False
        }
        
        start_time = time.time()
        
        # パターン1: 直接接続（プロキシなし）
        if not self._cancelled:
            self.progress_updated.emit("パターン1: 直接接続テスト中...", 10)
            results['pattern1_direct'] = self._test_pattern1_direct()
            time.sleep(0.5)
        
        # パターン2: プロキシ経由（CA証明書なし・SSL検証あり）
        if not self._cancelled:
            self.progress_updated.emit("パターン2: プロキシ（CA無・検証ON）テスト中...", 35)
            results['pattern2_proxy_no_ca_verify_on'] = self._test_pattern2_proxy_no_ca_verify_on()
            time.sleep(0.5)
        
        # パターン3: プロキシ経由（CA証明書なし・SSL検証なし）
        if not self._cancelled:
            self.progress_updated.emit("パターン3: プロキシ（CA無・検証OFF）テスト中...", 60)
            results['pattern3_proxy_no_ca_verify_off'] = self._test_pattern3_proxy_no_ca_verify_off()
            time.sleep(0.5)
        
        # パターン4: プロキシ経由（CA証明書あり・truststore使用・SSL検証あり）
        if not self._cancelled:
            self.progress_updated.emit("パターン4: プロキシ（CA有）テスト中...", 85)
            results['pattern4_proxy_with_ca'] = self._test_pattern4_proxy_with_ca()
        
        # 全体の成功判定（いずれか1つでも成功すればOK）
        results['overall_success'] = (
            results['pattern1_direct']['success'] or
            results['pattern2_proxy_no_ca_verify_on']['success'] or
            results['pattern3_proxy_no_ca_verify_off']['success'] or
            results['pattern4_proxy_with_ca']['success']
        )
        
        # 完了通知
        self.progress_updated.emit("テスト完了", 100)
        self.test_completed.emit(results)
    
    def _test_pattern1_direct(self) -> dict:
        """パターン1: 直接接続（プロキシなし）"""
        try:
            import requests
            import time
            
            start_time = time.time()
            
            # 直接接続（プロキシなし）- 新規セッション作成
            session = requests.Session()
            session.proxies = {}  # プロキシ明示的に無効
            session.trust_env = False  # 環境変数・システムプロキシも無視
            session.verify = True  # SSL検証有効
            
            # テスト用ヘッダを適用
            headers = self._get_test_headers()
            
            try:
                response = session.get(self.test_url, headers=headers, timeout=self.timeout)
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    logger.info(f"[接続テスト] パターン1成功: 直接接続 ({elapsed:.2f}秒)")
                    return {
                        'success': True,
                        'message': f'成功 ({elapsed:.2f}秒)',
                        'details': f'✅ 直接接続成功\nURL: {self.test_url}\nStatus: 200\n応答時間: {elapsed:.2f}秒',
                        'time': elapsed
                    }
                else:
                    error_msg = f'HTTP {response.status_code}'
                    logger.warning(f"[接続テスト] パターン1失敗: {error_msg}")
                    return {
                        'success': False,
                        'message': error_msg,
                        'details': f'❌ HTTP Status: {response.status_code}',
                        'time': elapsed
                    }
            except Exception as e:
                elapsed = time.time() - start_time
                error_type = type(e).__name__
                error_msg = str(e)
                logger.error(f"[接続テスト] パターン1失敗: {error_type}: {error_msg}")
                return {
                    'success': False,
                    'message': f'接続失敗 ({elapsed:.1f}秒)',
                    'details': f'❌ エラー: {error_msg}\nエラータイプ: {error_type}',
                    'time': elapsed
                }
            finally:
                session.close()
                
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"[接続テスト] パターン1テストエラー: {error_type}: {error_msg}")
            return {
                'success': False,
                'message': 'テストエラー',
                'details': f'❌ エラー: {error_msg}\nエラータイプ: {error_type}',
                'time': 0
            }
    
    def _test_pattern2_proxy_no_ca_verify_on(self) -> dict:
        """パターン2: プロキシ経由（CA証明書なし・truststore不使用・SSL検証あり）"""
        try:
            import requests
            import time
            
            # プロキシ設定を取得
            proxies = self._get_proxy_config()
            if not proxies:
                logger.info("[接続テスト] パターン2スキップ: プロキシ未設定")
                return {
                    'success': False,
                    'message': 'プロキシ未設定',
                    'details': '⏹️ プロキシが設定されていないためスキップ',
                    'time': 0
                }
            
            start_time = time.time()
            
            # プロキシ経由・SSL検証ON・truststore無効 - 新規セッション作成
            session = requests.Session()
            session.proxies = proxies
            session.trust_env = False  # 環境変数・システムプロキシを無視（明示的なプロキシのみ使用）
            session.verify = True  # SSL検証有効
            # truststoreは意図的に使用しない
            
            # テスト用ヘッダを適用
            headers = self._get_test_headers()
            
            try:
                response = session.get(self.test_url, headers=headers, timeout=self.timeout)
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    logger.info(f"[接続テスト] パターン2成功: プロキシ（CA無・検証ON） ({elapsed:.2f}秒)")
                    return {
                        'success': True,
                        'message': f'成功 ({elapsed:.2f}秒)',
                        'details': f'✅ プロキシ接続成功（SSL検証ON・CA無）\nProxy: {proxies}\nStatus: 200\n応答時間: {elapsed:.2f}秒',
                        'time': elapsed
                    }
                else:
                    error_msg = f'HTTP {response.status_code}'
                    logger.warning(f"[接続テスト] パターン2失敗: {error_msg}")
                    return {
                        'success': False,
                        'message': error_msg,
                        'details': f'❌ HTTP Status: {response.status_code}\nProxy: {proxies}',
                        'time': elapsed
                    }
            except Exception as e:
                elapsed = time.time() - start_time
                error_type = type(e).__name__
                error_msg = str(e)
                
                # SSL証明書エラーかチェック
                if 'CERTIFICATE_VERIFY_FAILED' in error_msg or 'SSLError' in error_type:
                    logger.warning(f"[接続テスト] パターン2失敗（予想通り）: SSL証明書エラー - {error_type}")
                    details = f'❌ SSL証明書エラー（予想通り）\nProxy: {proxies}\nエラー: {error_msg}\nエラータイプ: {error_type}\n\n💡 CA証明書が必要です'
                else:
                    logger.error(f"[接続テスト] パターン2失敗: {error_type}: {error_msg}")
                    details = f'❌ 接続失敗\nProxy: {proxies}\nエラー: {error_msg}\nエラータイプ: {error_type}'
                
                return {
                    'success': False,
                    'message': f'接続失敗 ({elapsed:.1f}秒)',
                    'details': details,
                    'time': elapsed
                }
            finally:
                session.close()
                
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"[接続テスト] パターン2テストエラー: {error_type}: {error_msg}")
            return {
                'success': False,
                'message': 'テストエラー',
                'details': f'❌ エラー: {error_msg}\nエラータイプ: {error_type}',
                'time': 0
            }
    
    def _test_pattern3_proxy_no_ca_verify_off(self) -> dict:
        """パターン3: プロキシ経由（CA証明書なし・truststore不使用・SSL検証なし）"""
        try:
            import requests
            import urllib3
            import time
            
            # SSL警告を抑制
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # プロキシ設定を取得
            proxies = self._get_proxy_config()
            if not proxies:
                logger.info("[接続テスト] パターン3スキップ: プロキシ未設定")
                return {
                    'success': False,
                    'message': 'プロキシ未設定',
                    'details': '⏹️ プロキシが設定されていないためスキップ',
                    'time': 0
                }
            
            start_time = time.time()
            
            # プロキシ経由・SSL検証OFF - 新規セッション作成
            session = requests.Session()
            session.proxies = proxies
            session.trust_env = False  # 環境変数・システムプロキシを無視（明示的なプロキシのみ使用）
            session.verify = False  # SSL検証無効
            
            # テスト用ヘッダを適用
            headers = self._get_test_headers()
            
            try:
                response = session.get(self.test_url, headers=headers, timeout=self.timeout)
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    logger.warning(f"[接続テスト] パターン3成功（非推奨）: プロキシ（CA無・検証OFF） ({elapsed:.2f}秒) - セキュリティリスクあり")
                    return {
                        'success': True,
                        'message': f'成功 ({elapsed:.2f}秒)',
                        'details': f'⚠️ プロキシ接続成功（SSL検証OFF）\nProxy: {proxies}\nStatus: 200\n応答時間: {elapsed:.2f}秒\n\n⚠️ 警告: SSL検証を無効にしています。セキュリティリスクがあります。',
                        'time': elapsed
                    }
                else:
                    logger.warning(f"[接続テスト] パターン3失敗: HTTP {response.status_code}")
                    return {
                        'success': False,
                        'message': f'HTTP {response.status_code}',
                        'details': f'❌ HTTP Status: {response.status_code}\nProxy: {proxies}',
                        'time': elapsed
                    }
            except Exception as e:
                elapsed = time.time() - start_time
                error_type = type(e).__name__
                error_msg = str(e)
                logger.error(f"[接続テスト] パターン3失敗（SSL検証OFFでも失敗）: {error_type}: {error_msg}")
                return {
                    'success': False,
                    'message': f'接続失敗 ({elapsed:.1f}秒)',
                    'details': f'❌ 接続失敗（SSL検証OFFでも失敗）\nProxy: {proxies}\nエラー: {str(e)}',
                    'time': elapsed
                }
            finally:
                session.close()
                
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"[接続テスト] パターン3テストエラー: {error_type}: {error_msg}")
            return {
                'success': False,
                'message': 'テストエラー',
                'details': f'❌ エラー: {str(e)}',
                'time': 0
            }
    
    def _test_pattern4_proxy_with_ca(self) -> dict:
        """パターン4: プロキシ経由（CA証明書あり・truststore使用・SSL検証あり）"""
        try:
            import requests
            import time
            
            # プロキシ設定を取得
            proxies = self._get_proxy_config()
            if not proxies:
                logger.info("[接続テスト] パターン4スキップ: プロキシ未設定")
                return {
                    'success': False,
                    'message': 'プロキシ未設定',
                    'details': '⏹️ プロキシが設定されていないためスキップ',
                    'time': 0
                }
            
            # truststore設定を確認
            cert_config = self.proxy_config.get('cert', {})
            use_truststore = cert_config.get('enterprise_ca', {}).get('enable_truststore', False)
            custom_ca = cert_config.get('enterprise_ca', {}).get('custom_ca_bundle', '')
            
            # truststoreを有効化
            if use_truststore:
                try:
                    import truststore
                    truststore.inject_into_ssl()
                    ca_info = "truststore (Windows証明書ストア) 有効化済み"
                    logger.info("[接続テスト] パターン4: truststore有効化成功")
                except ImportError:
                    ca_info = "truststore未インストール"
                    use_truststore = False
                    logger.warning("[接続テスト] パターン4: truststore未インストール")
                except Exception as e:
                    ca_info = "truststore有効化失敗"
                    use_truststore = False
                    logger.error(f"[接続テスト] パターン4: truststore有効化失敗 - {type(e).__name__}: {str(e)}")
            else:
                ca_info = "truststore無効"
                logger.info("[接続テスト] パターン4: truststore無効状態でテスト開始")
            
            start_time = time.time()
            
            # プロキシ経由・SSL検証ON・CA証明書あり - 新規セッション作成
            session = requests.Session()
            session.proxies = proxies
            session.trust_env = False  # 環境変数・システムプロキシを無視（明示的なプロキシのみ使用）
            
            # カスタムCA証明書の指定
            if custom_ca:
                import os
                if os.path.exists(custom_ca):
                    session.verify = custom_ca
                    ca_info += f" + カスタムCA: {custom_ca}"
                    logger.info(f"[接続テスト] パターン4: カスタムCAファイル使用 - {custom_ca}")
                else:
                    session.verify = True
                    ca_info += " (カスタムCAファイル未発見)"
                    logger.warning(f"[接続テスト] パターン4: カスタムCAファイル未発見 - {custom_ca}")
            else:
                session.verify = True
            
            # テスト用ヘッダを適用
            headers = self._get_test_headers()
            
            try:
                response = session.get(self.test_url, headers=headers, timeout=self.timeout)
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    logger.info(f"[接続テスト] パターン4成功: プロキシ（CA有・truststore有・検証ON） ({elapsed:.2f}秒)")
                    return {
                        'success': True,
                        'message': f'成功 ({elapsed:.2f}秒)',
                        'details': f'✅ プロキシ接続成功（CA証明書あり）\nProxy: {proxies}\nCA: {ca_info}\nStatus: 200\n応答時間: {elapsed:.2f}秒',
                        'time': elapsed
                    }
                else:
                    logger.warning(f"[接続テスト] パターン4失敗: HTTP {response.status_code}")
                    return {
                        'success': False,
                        'message': f'HTTP {response.status_code}',
                        'details': f'❌ HTTP Status: {response.status_code}\nProxy: {proxies}\nCA: {ca_info}',
                        'time': elapsed
                    }
            except Exception as e:
                elapsed = time.time() - start_time
                error_type = type(e).__name__
                error_msg = str(e)
                
                # SSL証明書エラーかチェック
                if 'CERTIFICATE_VERIFY_FAILED' in error_msg or 'SSLError' in error_type:
                    logger.error(f"[接続テスト] パターン4失敗: SSL証明書エラー - {error_type}: {error_msg}")
                    details = f'❌ SSL証明書エラー\nProxy: {proxies}\nCA: {ca_info}\nエラー: {error_msg}\n\n💡 CA証明書が正しくないか、中間証明書が不足している可能性があります'
                else:
                    logger.error(f"[接続テスト] パターン4失敗: {error_type}: {error_msg}")
                    details = f'❌ 接続失敗\nProxy: {proxies}\nCA: {ca_info}\nエラー: {error_msg}'
                
                return {
                    'success': False,
                    'message': f'接続失敗 ({elapsed:.1f}秒)',
                    'details': details,
                    'time': elapsed
                }
            finally:
                session.close()
                
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"[接続テスト] パターン4テストエラー: {error_type}: {error_msg}")
            return {
                'success': False,
                'message': 'テストエラー',
                'details': f'❌ エラー: {str(e)}',
                'time': 0
            }
    
    def _get_test_headers(self) -> Dict[str, str]:
        """テスト用ヘッダを取得"""
        if self.header_pattern == 'custom':
            return self.custom_headers.copy()
        
        from classes.config.conf.connection_test_headers import get_header_pattern
        return get_header_pattern(self.header_pattern)
    
    def _get_proxy_config(self) -> dict:
        """プロキシ設定を取得"""
        mode = self.proxy_config.get('mode', 'DIRECT').upper()
        
        if mode == 'HTTP':
            # 手動プロキシ設定
            http_proxy = self.proxy_config.get('http_proxy', '')
            https_proxy = self.proxy_config.get('https_proxy', http_proxy)
            
            if not http_proxy:
                return {}
            
            return {
                'http': http_proxy,
                'https': https_proxy
            }
            
        elif mode == 'SYSTEM':
            # システムプロキシ使用
            try:
                from urllib.request import getproxies
                system_proxies = getproxies()
                http_proxy = system_proxies.get('http', '')
                https_proxy = system_proxies.get('https', http_proxy)
                
                if not http_proxy:
                    return {}
                
                return {
                    'http': http_proxy,
                    'https': https_proxy
                }
            except Exception:
                return {}
                
        else:
            # DIRECT モードや その他
            return {}
    
    def cancel(self):
        """テストをキャンセル"""
        self._cancelled = True


class ProxySettingsWidget(QWidget):
    """プロキシ設定ウィジェット"""
    
    def __init__(self, parent=None):
        if not PYQT5_AVAILABLE:
            logger.warning("PyQt5が利用できないため、プロキシ設定ウィジェットを初期化できません")
            super().__init__() if QWidget != type else None
            return
            
        super().__init__(parent)
        self.current_config = {}
        self.test_worker = None
        self.init_ui()
        self.load_current_settings()
        
    def init_ui(self):
        """UI初期化"""
        if not PYQT5_AVAILABLE:
            return
            
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # タイトル
        title_label = QLabel("プロキシ設定")
        title_label.setFont(QFont())  # システム標準フォントを使用
        layout.addWidget(title_label)
        
        # 簡易設定（Fiddler等のテスト用）
        self.setup_quick_config_section(layout)
        
        # 現在の状態表示
        self.setup_status_section(layout)
        
        # SSL証明書詳細情報
        self.setup_ssl_certificate_details_section(layout)
        
        # 企業CA設定
        self.setup_enterprise_ca_section(layout)
        
        # プロキシモード設定
        self.setup_mode_section(layout)
        
        # プロキシ詳細設定
        self.setup_proxy_details_section(layout)
        
        # プリセット管理
        self.setup_preset_section(layout)
        
        # 接続テスト
        self.setup_test_section(layout)
        
        # 操作ボタン
        self.setup_action_buttons(layout)
        
        # ログ表示
        self.setup_log_section(layout)
    
    def setup_quick_config_section(self, layout):
        """簡易設定セクション（Fiddler等のテスト用）"""
        quick_group = QGroupBox("🚀 簡易設定（テスト用）")
        quick_group.setStyleSheet(f"QGroupBox {{ font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}")
        quick_layout = QVBoxLayout(quick_group)
        
        # 説明ラベル
        info_label = QLabel(
            "Fiddler等のプロキシツールでテストする際に便利な設定です。\n"
            "ワンクリックで推奨設定を適用できます。"
        )
        info_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px;")
        quick_layout.addWidget(info_label)
        
        # ボタンレイアウト
        button_layout = QHBoxLayout()
        
        # Fiddler設定ボタン
        fiddler_btn = QPushButton("📡 Fiddler設定 (localhost:8888 + OS証明書)")
        fiddler_btn.setStyleSheet(f"background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)}; font-weight: bold; padding: 8px;")
        fiddler_btn.setToolTip(
            "Fiddler用の推奨設定:\n"
            "・HTTPプロキシ: http://localhost:8888\n"
            "・SSL検証: 有効\n"
            "・OS証明書ストア使用: 有効"
        )
        fiddler_btn.clicked.connect(self.apply_fiddler_quick_config)
        button_layout.addWidget(fiddler_btn)
        
        # プロキシなし設定ボタン
        direct_btn = QPushButton("🔓 プロキシなし（直接接続）")
        direct_btn.setStyleSheet(f"background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)}; font-weight: bold; padding: 8px;")
        direct_btn.setToolTip("プロキシを使用せず直接インターネットに接続")
        direct_btn.clicked.connect(self.apply_direct_quick_config)
        button_layout.addWidget(direct_btn)
        
        # プロキシあり・SSL無効ボタン
        no_ssl_btn = QPushButton("⚠️ プロキシあり・SSL検証無効")
        no_ssl_btn.setStyleSheet(f"background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)}; font-weight: bold; padding: 8px;")
        no_ssl_btn.setToolTip(
            "CAなしプロキシ用:\n"
            "・現在のプロキシ設定を維持\n"
            "・SSL検証を無効化"
        )
        no_ssl_btn.clicked.connect(self.apply_no_ssl_quick_config)
        button_layout.addWidget(no_ssl_btn)
        
        quick_layout.addLayout(button_layout)
        
        layout.addWidget(quick_group)
        
    def setup_status_section(self, layout):
        """現在の状態表示セクション - OS設定とアプリ設定を区別して表示"""
        status_group = QGroupBox("現在のプロキシ状態")
        status_layout = QGridLayout(status_group)
        
        # ========== アプリケーション設定セクション ==========
        app_header = QLabel("【アプリケーション設定】")
        app_header.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.PANEL_SUCCESS_TEXT)}; font-size: 12px;")
        status_layout.addWidget(app_header, 0, 0, 1, 2)
        
        # 現在のモード
        status_layout.addWidget(QLabel("プロキシモード:"), 1, 0)
        self.current_mode_label = QLabel("読み込み中...")
        self.current_mode_label.setStyleSheet("font-weight: bold; color: blue;")
        status_layout.addWidget(self.current_mode_label, 1, 1)
        
        # 現在のプロキシ
        status_layout.addWidget(QLabel("HTTPプロキシ:"), 2, 0)
        self.current_http_proxy_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_http_proxy_label, 2, 1)
        
        status_layout.addWidget(QLabel("HTTPSプロキシ:"), 3, 0)
        self.current_https_proxy_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_https_proxy_label, 3, 1)
        
        # SSL証明書の状態
        status_layout.addWidget(QLabel("SSL証明書検証:"), 4, 0)
        self.current_ssl_verify_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_ssl_verify_label, 4, 1)
        
        status_layout.addWidget(QLabel("証明書ストア:"), 5, 0)
        self.current_cert_store_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_cert_store_label, 5, 1)
        
        # 環境変数信頼設定
        status_layout.addWidget(QLabel("環境変数信頼:"), 6, 0)
        self.current_trust_env_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_trust_env_label, 6, 1)
        
        # ========== OS/システム設定セクション ==========
        os_header = QLabel("【OS/システム設定】")
        os_header.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-size: 12px; margin-top: 10px;")
        status_layout.addWidget(os_header, 7, 0, 1, 2)
        
        # OSプロキシ設定
        status_layout.addWidget(QLabel("OS HTTPプロキシ:"), 8, 0)
        self.os_http_proxy_label = QLabel("取得中...")
        self.os_http_proxy_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        status_layout.addWidget(self.os_http_proxy_label, 8, 1)
        
        status_layout.addWidget(QLabel("OS HTTPSプロキシ:"), 9, 0)
        self.os_https_proxy_label = QLabel("取得中...")
        self.os_https_proxy_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        status_layout.addWidget(self.os_https_proxy_label, 9, 1)
        
        # 環境変数プロキシ設定
        status_layout.addWidget(QLabel("環境変数 HTTP_PROXY:"), 10, 0)
        self.env_http_proxy_label = QLabel("取得中...")
        self.env_http_proxy_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        status_layout.addWidget(self.env_http_proxy_label, 10, 1)
        
        status_layout.addWidget(QLabel("環境変数 HTTPS_PROXY:"), 11, 0)
        self.env_https_proxy_label = QLabel("取得中...")
        self.env_https_proxy_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        status_layout.addWidget(self.env_https_proxy_label, 11, 1)
        
        # ボタン行
        button_layout = QHBoxLayout()
        
        # システムプロキシ検出ボタン
        detect_btn = QPushButton("システムプロキシ検出")
        detect_btn.clicked.connect(self.detect_system_proxy)
        button_layout.addWidget(detect_btn)
        
        # 実際の適用状態表示ボタン
        show_active_btn = QPushButton("📊 実際に適用されているプロキシを表示")
        show_active_btn.setStyleSheet(f"font-weight: bold; background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};")
        show_active_btn.clicked.connect(self.show_active_proxy_status)
        button_layout.addWidget(show_active_btn)
        
        status_layout.addLayout(button_layout, 12, 0, 1, 2)
        
        layout.addWidget(status_group)
        
    def setup_ssl_certificate_details_section(self, layout):
        """SSL証明書詳細情報セクション"""
        cert_group = QGroupBox("SSL証明書詳細情報")
        cert_layout = QGridLayout(cert_group)
        
        # 証明書バンドルパス
        cert_layout.addWidget(QLabel("証明書バンドルパス:"), 0, 0)
        self.cert_bundle_path_label = QLabel("読み込み中...")
        self.cert_bundle_path_label.setWordWrap(True)
        self.cert_bundle_path_label.setStyleSheet(f"font-family: monospace; font-size: 10px; color: {get_color(ThemeKey.TEXT_MUTED)};")
        cert_layout.addWidget(self.cert_bundle_path_label, 0, 1)
        
        # 証明書情報
        cert_layout.addWidget(QLabel("証明書情報:"), 1, 0)
        self.cert_info_label = QLabel("読み込み中...")
        cert_layout.addWidget(self.cert_info_label, 1, 1)
        
        # 使用中の証明書ライブラリ
        cert_layout.addWidget(QLabel("証明書ライブラリ:"), 2, 0)
        self.cert_library_label = QLabel("読み込み中...")
        cert_layout.addWidget(self.cert_library_label, 2, 1)
        
        # SSL戦略詳細
        cert_layout.addWidget(QLabel("SSL処理戦略:"), 3, 0)
        self.ssl_strategy_label = QLabel("読み込み中...")
        cert_layout.addWidget(self.ssl_strategy_label, 3, 1)
        
        # 証明書テストボタン
        cert_test_btn = QPushButton("証明書バンドルを確認")
        cert_test_btn.clicked.connect(self.test_certificate_bundle)
        cert_layout.addWidget(cert_test_btn, 4, 0, 1, 2)
        
        layout.addWidget(cert_group)
        
    def setup_enterprise_ca_section(self, layout):
        """組織内CA設定セクション"""
        enterprise_group = QGroupBox("組織内CA設定 (高度な設定)")
        enterprise_layout = QGridLayout(enterprise_group)
        
        # PAC設定（ラベル）
        pac_section = QLabel("PAC自動設定:")
        pac_section.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.PANEL_SUCCESS_TEXT)};")

        # チェックボックスを横並びにするためのコンテナ
        pac_container = QWidget()
        pac_hbox = QHBoxLayout(pac_container)
        pac_hbox.setContentsMargins(0, 0, 0, 0)
        pac_hbox.setSpacing(12)

        self.pac_auto_detect_checkbox = QCheckBox("PAC自動検出")
        self.pac_auto_detect_checkbox.setToolTip("プロキシ自動設定 (PAC) を自動検出")
        pac_hbox.addWidget(self.pac_auto_detect_checkbox)

        self.pac_fallback_checkbox = QCheckBox("PAC失敗時にシステムプロキシにフォールバック")
        self.pac_fallback_checkbox.setToolTip("PAC設定取得に失敗した場合のフォールバック動作")
        pac_hbox.addWidget(self.pac_fallback_checkbox)

        pac_hbox.addStretch()  # 右側余白で左寄せ

        # ★ 同じ行（row=0）に、左: ラベル / 右: チェックボックス群 を配置
        enterprise_layout.addWidget(pac_section,   0, 0, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
        enterprise_layout.addWidget(pac_container, 0, 1, 1, 1)
        
        # 組織内CA証明書（ラベル）
        ca_section = QLabel("組織内CA証明書:")
        ca_section.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.PANEL_SUCCESS_TEXT)};")

        # チェックボックスを横並びにするためのコンテナ
        ca_container = QWidget()
        ca_hbox = QHBoxLayout(ca_container)
        ca_hbox.setContentsMargins(0, 0, 0, 0)
        ca_hbox.setSpacing(12)

        self.enable_truststore_checkbox = QCheckBox("truststoreを使用")
        self.enable_truststore_checkbox.setToolTip("truststoreライブラリでシステム証明書を自動取得")
        ca_hbox.addWidget(self.enable_truststore_checkbox)

        self.auto_detect_corporate_ca_checkbox = QCheckBox("組織内CA自動検出")
        self.auto_detect_corporate_ca_checkbox.setToolTip("組織環境のCA証明書を自動検出してバンドルに追加")
        ca_hbox.addWidget(self.auto_detect_corporate_ca_checkbox)

        ca_hbox.addStretch()  # 右側の余白を埋めて左寄せにする

        # ★ 同じ行（row=3）に、左: ラベル / 右: チェックボックス群 を配置
        enterprise_layout.addWidget(ca_section,      3, 0, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
        enterprise_layout.addWidget(ca_container,    3, 1, 1, 1)

        # カスタムCA Bundle 入力欄（存在しないため定義）
        enterprise_layout.addWidget(QLabel("カスタムCA Bundle:"), 4, 0)
        self.custom_ca_bundle_edit = QLineEdit()
        self.custom_ca_bundle_edit.setPlaceholderText("カスタム証明書バンドルファイルのパス")
        enterprise_layout.addWidget(self.custom_ca_bundle_edit, 4, 1)




        # SSL戦略
        ssl_section = QLabel("SSL処理:")
        ssl_section.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.PANEL_SUCCESS_TEXT)};")

        enterprise_layout.addWidget(ssl_section, 7, 0)
        self.ssl_strategy_combo = QComboBox()
        self.ssl_strategy_combo.addItems([
            "use_proxy_ca - プロキシCA使用",
            "strict_verification - 厳密検証",
            "fallback_no_verify - フォールバック無検証"
        ])
        enterprise_layout.addWidget(self.ssl_strategy_combo, 7, 1)
        
        # 組織内CA機能テストボタン
        enterprise_test_layout = QHBoxLayout()
        
        test_pac_btn = QPushButton("PAC設定テスト (未実装)")
        test_pac_btn.clicked.connect(self.test_pac_configuration)
        test_pac_btn.setEnabled(False)  # 未実装のため無効化
        enterprise_test_layout.addWidget(test_pac_btn)
        
        test_ca_btn = QPushButton("組織内CA確認")
        test_ca_btn.clicked.connect(self.test_enterprise_ca)
        enterprise_test_layout.addWidget(test_ca_btn)
        
        enterprise_layout.addLayout(enterprise_test_layout, 8, 0, 1, 2)
        
        # 企業CA状況表示
        self.enterprise_ca_status_label = QLabel("組織内CA機能状況: 確認中...")
        self.enterprise_ca_status_label.setStyleSheet(f"font-size: 10px; color: {get_color(ThemeKey.TEXT_MUTED)};")
        enterprise_layout.addWidget(self.enterprise_ca_status_label, 9, 0, 1, 2)
        
        layout.addWidget(enterprise_group)
        
        # 企業CA機能状況を初期確認
        self.check_enterprise_ca_features()
        
    def setup_mode_section(self, layout):
        """プロキシモード設定セクション"""
        mode_group = QGroupBox("プロキシモード")
        mode_layout = QVBoxLayout(mode_group)
        
        self.mode_button_group = QButtonGroup(self)
        
        # DIRECT モード
        self.direct_radio = QRadioButton("DIRECT - プロキシを使用しない")
        self.mode_button_group.addButton(self.direct_radio, 0)
        mode_layout.addWidget(self.direct_radio)
        
        # SYSTEM モード
        self.system_radio = QRadioButton("SYSTEM - システムプロキシを自動使用")
        self.mode_button_group.addButton(self.system_radio, 1)
        mode_layout.addWidget(self.system_radio)
        
        # HTTP モード
        self.http_radio = QRadioButton("HTTP - 手動プロキシ設定")
        self.mode_button_group.addButton(self.http_radio, 2)
        mode_layout.addWidget(self.http_radio)
        
        # PAC モード
        self.pac_radio = QRadioButton("PAC - プロキシ自動設定")
        self.mode_button_group.addButton(self.pac_radio, 3)
        mode_layout.addWidget(self.pac_radio)
        
        # モード変更時のイベント
        self.mode_button_group.buttonClicked.connect(self.on_mode_changed)
        
        layout.addWidget(mode_group)
        
    def setup_proxy_details_section(self, layout):
        """プロキシ詳細設定セクション"""
        self.proxy_details_group = QGroupBox("プロキシ詳細設定")
        details_layout = QGridLayout(self.proxy_details_group)
        
        # HTTP プロキシ
        details_layout.addWidget(QLabel("HTTPプロキシ:"), 0, 0)
        self.http_proxy_edit = QLineEdit()
        self.http_proxy_edit.setPlaceholderText("http://proxy.example.com:8080")
        details_layout.addWidget(self.http_proxy_edit, 0, 1)
        
        # HTTPS プロキシ
        details_layout.addWidget(QLabel("HTTPSプロキシ:"), 1, 0)
        self.https_proxy_edit = QLineEdit()
        self.https_proxy_edit.setPlaceholderText("http://proxy.example.com:8080")
        details_layout.addWidget(self.https_proxy_edit, 1, 1)
        
        # 除外リスト
        details_layout.addWidget(QLabel("除外リスト:"), 2, 0)
        self.no_proxy_edit = QLineEdit()
        self.no_proxy_edit.setPlaceholderText("localhost,127.0.0.1,.local")
        details_layout.addWidget(self.no_proxy_edit, 2, 1)
        
        # HTTPSプロキシ同期チェックボックス
        self.sync_https_checkbox = QCheckBox("HTTPSプロキシをHTTPプロキシと同じにする")
        self.sync_https_checkbox.setChecked(True)
        self.sync_https_checkbox.toggled.connect(self.on_sync_https_toggled)
        details_layout.addWidget(self.sync_https_checkbox, 3, 0, 1, 2)
        
        # 入力変更時のイベント
        self.http_proxy_edit.textChanged.connect(self.on_proxy_details_changed)
        
        layout.addWidget(self.proxy_details_group)
        
    def setup_preset_section(self, layout):
        """プリセット管理セクション"""
        preset_group = QGroupBox("プリセット設定")
        preset_layout = QHBoxLayout(preset_group)
        
        preset_layout.addWidget(QLabel("プリセット:"))
        
        self.preset_combo = QComboBox()
        preset_layout.addWidget(self.preset_combo)
        
        apply_preset_btn = QPushButton("適用")
        apply_preset_btn.clicked.connect(self.apply_preset)
        preset_layout.addWidget(apply_preset_btn)
        
        save_preset_btn = QPushButton("現在設定を保存 (未実装)")
        save_preset_btn.clicked.connect(self.save_current_as_preset)
        save_preset_btn.setEnabled(False)  # 未実装のため無効化
        preset_layout.addWidget(save_preset_btn)
        
        layout.addWidget(preset_group)
        
    def setup_test_section(self, layout):
        """接続テストセクション"""
        test_group = QGroupBox("接続テスト")
        test_layout = QVBoxLayout(test_group)
        
        # 説明ラベル
        info_label = QLabel(
            "🔍 プロキシ設定の接続テストを実行します\n"
            "・Requests: HTTP通信ライブラリでの接続確認\n"
            "・WebView: ブラウザエンジンでの接続確認\n"
            "・統合診断: 包括的なプロキシ・SSL診断ツール"
        )
        info_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px;")
        test_layout.addWidget(info_label)
        
        # HTTPヘッダ設定
        header_layout = QGridLayout()
        header_layout.addWidget(QLabel("HTTPヘッダ:"), 0, 0)
        
        self.header_pattern_combo = QComboBox()
        self.header_pattern_combo.setToolTip("接続テストで使用するHTTPヘッダを選択")
        header_layout.addWidget(self.header_pattern_combo, 0, 1)
        
        # ヘッダパターン選択肢を追加
        from classes.config.conf.connection_test_headers import get_pattern_list
        for key, name, description in get_pattern_list():
            self.header_pattern_combo.addItem(f"{name} - {description}", key)
        
        # カスタムヘッダ入力欄
        header_layout.addWidget(QLabel("カスタムヘッダ:"), 1, 0)
        self.custom_headers_edit = QTextEdit()
        self.custom_headers_edit.setPlaceholderText(
            "カスタムヘッダ選択時に使用 (JSON形式)\n"
            "例:\n"
            "{\n"
            '  "User-Agent": "MyApp/1.0",\n'
            '  "Accept": "application/json"\n'
            "}"
        )
        self.custom_headers_edit.setMaximumHeight(80)
        self.custom_headers_edit.setEnabled(False)
        header_layout.addWidget(self.custom_headers_edit, 1, 1)
        
        # カスタムヘッダ有効化制御
        self.header_pattern_combo.currentIndexChanged.connect(self._on_header_pattern_changed)
        
        test_layout.addLayout(header_layout)
        
        # テストボタンとプログレスバー
        test_btn_layout = QHBoxLayout()
        
        self.test_button = QPushButton("🧪 接続テスト実行")
        self.test_button.clicked.connect(self.run_connection_test)
        self.test_button.setStyleSheet("font-weight: bold;")
        test_btn_layout.addWidget(self.test_button)
        
        self.test_webview_button = QPushButton("🌐 WebViewテスト実行")
        self.test_webview_button.clicked.connect(self.run_webview_test)
        test_btn_layout.addWidget(self.test_webview_button)
        
        # 統合診断ボタン（新規）
        self.diagnostic_button = QPushButton("🔍 統合診断を実行")
        self.diagnostic_button.clicked.connect(self.run_integrated_diagnostics)
        self.diagnostic_button.setStyleSheet(
            f"QPushButton {{ background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)}; font-weight: bold; padding: 8px; }}"
            f"QPushButton:hover {{ background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)}; }}"
        )
        self.diagnostic_button.setToolTip(
            "包括的なプロキシ・SSL診断を実行:\n"
            "・基本プロキシ診断\n"
            "・システムプロキシ検出\n"
            "・SSL/CA証明書診断\n"
            "・設定保存・読み込みフロー\n"
            "・連続接続安定性"
        )
        test_btn_layout.addWidget(self.diagnostic_button)
        
        self.test_progress = QProgressBar()
        self.test_progress.setVisible(False)
        test_btn_layout.addWidget(self.test_progress)
        
        test_layout.addLayout(test_btn_layout)
        
        # テスト結果表示エリア
        self.test_result_text = QTextEdit()
        self.test_result_text.setReadOnly(True)
        self.test_result_text.setMaximumHeight(200)
        self.test_result_text.setPlainText("テスト実行前")
        test_layout.addWidget(self.test_result_text)
        
        layout.addWidget(test_group)
        
    def setup_action_buttons(self, layout):
        """操作ボタンセクション"""
        button_layout = QHBoxLayout()
        
        apply_btn = QPushButton("設定を適用")
        apply_btn.clicked.connect(self.apply_settings)
        apply_btn.setStyleSheet(f"QPushButton {{ background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)}; font-weight: bold; }}")
        button_layout.addWidget(apply_btn)
        
        reload_btn = QPushButton("設定を再読み込み")
        reload_btn.clicked.connect(self.load_current_settings)
        button_layout.addWidget(reload_btn)
        
        reset_btn = QPushButton("デフォルトに戻す (未実装)")
        reset_btn.clicked.connect(self.reset_to_defaults)
        reset_btn.setEnabled(False)  # 未実装のため無効化
        button_layout.addWidget(reset_btn)
        
        layout.addLayout(button_layout)
        
    def setup_log_section(self, layout):
        """ログ表示セクション"""
        log_group = QGroupBox("ログ")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        clear_log_btn = QPushButton("ログクリア")
        clear_log_btn.clicked.connect(self.clear_log)
        log_layout.addWidget(clear_log_btn)
        
        layout.addWidget(log_group)
        
    def load_current_settings(self):
        """現在の設定を読み込み"""
        try:
            from net.session_manager import ProxySessionManager
            
            manager = ProxySessionManager()
            self.current_config = manager.get_proxy_config()
            
            if not self.current_config:
                # 設定ファイルから直接読み込み
                manager.configure()
                self.current_config = manager.get_proxy_config()
            
            self.update_ui_from_config()
            self.load_presets()
            self.add_log("設定を読み込みました")
            
        except Exception as e:
            self.add_log(f"設定読み込みエラー: {e}")
            logger.error(f"設定読み込みエラー: {e}")
            
    def load_presets(self):
        """プリセット一覧を読み込み"""
        try:
            from config.common import get_dynamic_file_path
            import yaml
            
            yaml_path = get_dynamic_file_path("config/network.yaml")
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    
                configurations = data.get('configurations', {})
                
                self.preset_combo.clear()
                self.preset_combo.addItem("-- プリセット選択 --", None)
                
                for name, config in configurations.items():
                    mode = config.get('mode', 'UNKNOWN')
                    display_name = f"{name} ({mode})"
                    self.preset_combo.addItem(display_name, name)
                    
        except Exception as e:
            self.add_log(f"プリセット読み込みエラー: {e}")
            
    def update_ssl_certificate_status(self):
        """SSL証明書の使用状況を更新"""
        try:
            cert_config = self.current_config.get('cert', {})
            
            # SSL検証状態
            ssl_verify = cert_config.get('verify', True)
            if ssl_verify:
                verify_text = "有効"
                verify_style = "color: green; font-weight: bold;"
            else:
                verify_text = "無効"
                verify_style = "color: red; font-weight: bold;"
            
            self.current_ssl_verify_label.setText(verify_text)
            self.current_ssl_verify_label.setStyleSheet(verify_style)
            
            # 証明書ストア情報
            use_os_store = cert_config.get('use_os_store', False)
            ca_bundle = cert_config.get('ca_bundle', '')
            proxy_ssl_handling = cert_config.get('proxy_ssl_handling', {})
            ssl_strategy = proxy_ssl_handling.get('strategy', 'default')
            
            # 証明書ストアの詳細表示
            cert_store_parts = []
            
            if ssl_verify:
                if ca_bundle:
                    cert_store_parts.append(f"カスタムCA: {os.path.basename(ca_bundle)}")
                elif use_os_store:
                    cert_store_parts.append("OSストア")
                else:
                    # certifi等のデフォルト
                    try:
                        import certifi
                        cert_store_parts.append("certifi")
                    except ImportError:
                        cert_store_parts.append("デフォルト")
                
                # プロキシ環境での戦略も表示
                if ssl_strategy != 'default':
                    strategy_names = {
                        'disable_verify': '検証無効',
                        'use_proxy_ca': 'プロキシCA',
                        'ignore_proxy': 'プロキシ無視'
                    }
                    strategy_display = strategy_names.get(ssl_strategy, ssl_strategy)
                    cert_store_parts.append(f"戦略:{strategy_display}")
            else:
                cert_store_parts.append("検証無効のため未使用")
            
            cert_store_text = " | ".join(cert_store_parts) if cert_store_parts else "不明"
            
            # プロキシ環境かどうかの判定
            mode = self.current_config.get('mode', 'DIRECT').upper()
            if mode == 'SYSTEM':
                from urllib.request import getproxies
                system_proxies = getproxies()
                is_proxy_env = bool(system_proxies.get('http') or system_proxies.get('https'))
            else:
                proxies_config = self.current_config.get('proxies', {})
                is_proxy_env = bool(proxies_config.get('http') or proxies_config.get('https'))
            
            if is_proxy_env:
                cert_store_text = f"🔗 プロキシ環境: {cert_store_text}"
            else:
                cert_store_text = f"📡 直接接続: {cert_store_text}"
            
            self.current_cert_store_label.setText(cert_store_text)
            
            # プロキシ環境でSSL有効の場合は警告表示
            if is_proxy_env and ssl_verify:
                self.current_cert_store_label.setStyleSheet("color: orange; font-size: 11px;")
                self.current_cert_store_label.setToolTip("プロキシ環境でSSL検証が有効です。接続問題が発生する可能性があります。")
            else:
                self.current_cert_store_label.setStyleSheet(f"color: {get_color(ThemeKey.INPUT_TEXT)}; font-size: 11px;")
                self.current_cert_store_label.setToolTip("")
                
        except Exception as e:
            self.current_ssl_verify_label.setText("取得エラー")
            self.current_cert_store_label.setText(f"エラー: {e}")
            logger.error(f"SSL証明書状態更新エラー: {e}")
    
    def update_ssl_certificate_details(self):
        """SSL証明書詳細情報を更新"""
        try:
            cert_config = self.current_config.get('cert', {})
            ssl_verify = cert_config.get('verify', True)
            
            # 実際に使用される証明書バンドルパスを取得
            from net.session_manager import ProxySessionManager
            manager = ProxySessionManager()
            session = manager.get_session()
            
            cert_bundle_path = "不明"
            cert_info = "情報取得中..."
            cert_library = "不明"
            ssl_strategy_info = "不明"
            
            # 使用中の証明書バンドル情報
            if ssl_verify:
                if hasattr(session, 'verify') and session.verify:
                    if isinstance(session.verify, str):
                        # カスタム証明書ファイル
                        cert_bundle_path = session.verify
                        if os.path.exists(cert_bundle_path):
                            file_size = os.path.getsize(cert_bundle_path)
                            import datetime
                            mtime = os.path.getmtime(cert_bundle_path)
                            mtime_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                            cert_info = f"サイズ: {file_size:,} bytes | 更新日: {mtime_str}"
                        else:
                            cert_info = "ファイルが存在しません"
                    else:
                        # デフォルト証明書
                        try:
                            import certifi
                            cert_bundle_path = certifi.where()
                            file_size = os.path.getsize(cert_bundle_path)
                            import datetime
                            mtime = os.path.getmtime(cert_bundle_path)
                            mtime_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                            
                            # certifiのバージョンも取得
                            import certifi
                            certifi_version = getattr(certifi, '__version__', 'Unknown')
                            
                            cert_info = f"サイズ: {file_size:,} bytes | 更新日: {mtime_str}"
                            cert_library = f"certifi v{certifi_version}"
                        except ImportError:
                            cert_bundle_path = "システムデフォルト"
                            cert_info = "certifi利用不可"
                            cert_library = "システム標準"
                        except Exception as e:
                            cert_info = f"取得エラー: {e}"
                else:
                    cert_bundle_path = "検証無効"
                    cert_info = "SSL検証が無効のため使用されません"
                    cert_library = "未使用"
            else:
                cert_bundle_path = "検証無効"
                cert_info = "SSL検証が無効のため使用されません"
                cert_library = "未使用"
            
            # SSL戦略情報
            proxy_ssl_handling = cert_config.get('proxy_ssl_handling', {})
            strategy = proxy_ssl_handling.get('strategy', 'default')
            fallback = proxy_ssl_handling.get('fallback_to_no_verify', False)
            log_errors = proxy_ssl_handling.get('log_ssl_errors', True)
            
            strategy_details = {
                'disable_verify': 'SSL検証を完全無効化',
                'use_proxy_ca': 'プロキシ証明書処理 + フォールバック',
                'ignore_proxy': 'プロキシを無視してSSL設定適用',
                'default': 'デフォルト戦略'
            }
            
            strategy_name = strategy_details.get(strategy, strategy)
            if fallback and strategy_name:
                strategy_name += " (フォールバック有効)"
            
            ssl_strategy_info = strategy_name
            
            # UI更新
            self.cert_bundle_path_label.setText(cert_bundle_path)
            self.cert_info_label.setText(cert_info)
            self.cert_library_label.setText(cert_library)
            self.ssl_strategy_label.setText(ssl_strategy_info)
            
        except Exception as e:
            self.cert_bundle_path_label.setText(f"エラー: {e}")
            self.cert_info_label.setText("取得失敗")
            self.cert_library_label.setText("取得失敗")
            self.ssl_strategy_label.setText("取得失敗")
            logger.error(f"SSL証明書詳細更新エラー: {e}")
    
    def test_certificate_bundle(self):
        """証明書バンドルのテスト"""
        try:
            from net.session_manager import ProxySessionManager
            manager = ProxySessionManager()
            session = manager.get_session()
            
            if hasattr(session, 'verify') and session.verify:
                if isinstance(session.verify, str) and os.path.exists(session.verify):
                    # 証明書ファイルの内容確認
                    with open(session.verify, 'r', encoding='utf-8') as f:
                        content = f.read()
                        cert_count = content.count('BEGIN CERTIFICATE')
                        
                    QMessageBox.information(self, "証明書バンドル情報",
                                          f"証明書ファイル: {session.verify}\n"
                                          f"証明書数: {cert_count}件\n"
                                          f"ファイルサイズ: {len(content):,} 文字")
                else:
                    QMessageBox.information(self, "証明書バンドル情報",
                                          f"証明書設定: {session.verify}\n"
                                          "（システムデフォルト証明書を使用）")
            else:
                QMessageBox.warning(self, "証明書バンドル情報",
                                  "SSL証明書検証が無効のため、証明書バンドルは使用されていません")
                
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"証明書バンドル情報取得エラー: {e}")
            
    def on_mode_changed(self):
        """プロキシモード変更時の処理"""
        if self.http_radio.isChecked():
            self.proxy_details_group.setEnabled(True)
        else:
            self.proxy_details_group.setEnabled(False)
            
        # PAC設定についてのヒント表示
        if hasattr(self, 'pac_radio') and self.pac_radio.isChecked():
            self.add_log("PAC自動設定モードを選択しました。組織内CA設定セクションでPAC自動検出を有効化してください。")
            
    def on_sync_https_toggled(self):
        """HTTPS同期チェックボックス変更時の処理"""
        if self.sync_https_checkbox.isChecked():
            self.https_proxy_edit.setEnabled(False)
            self.https_proxy_edit.setText(self.http_proxy_edit.text())
        else:
            self.https_proxy_edit.setEnabled(True)
            
    def on_proxy_details_changed(self):
        """プロキシ詳細変更時の処理"""
        if self.sync_https_checkbox.isChecked():
            self.https_proxy_edit.setText(self.http_proxy_edit.text())
    
    def _on_header_pattern_changed(self):
        """ヘッダパターン変更時の処理"""
        pattern_key = self.header_pattern_combo.currentData()
        # カスタムヘッダ選択時のみ入力欄を有効化
        self.custom_headers_edit.setEnabled(pattern_key == 'custom')
            
    def detect_system_proxy(self):
        """システムプロキシ検出"""
        try:
            from net.session_manager import ProxySessionManager
            
            manager = ProxySessionManager()
            proxy_info = manager.get_system_proxy_info()
            
            if proxy_info.get('detected', False):
                proxies = proxy_info.get('proxies', {})
                self.add_log(f"システムプロキシ検出: {proxies}")
                
                # 検出されたプロキシを入力欄に設定
                http_proxy = proxies.get('http', '')
                https_proxy = proxies.get('https', '')
                
                if http_proxy:
                    self.http_proxy_edit.setText(http_proxy)
                if https_proxy:
                    self.https_proxy_edit.setText(https_proxy)
                    
                QMessageBox.information(self, "システムプロキシ検出",
                                      f"システムプロキシを検出しました:\nHTTP: {http_proxy}\nHTTPS: {https_proxy}")
            else:
                self.add_log("システムプロキシが検出されませんでした")
                QMessageBox.information(self, "システムプロキシ検出",
                                      "システムプロキシが検出されませんでした")
                
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_error_message(f"システムプロキシ検出エラー: {error_msg}", max_line_length=80)
            
            self.add_log(formatted_error)
            QMessageBox.warning(self, "エラー", formatted_error)
    
    def show_active_proxy_status(self):
        """実際に適用されているプロキシ設定を表示"""
        try:
            from net.session_manager import get_active_proxy_status
            
            # 現在アクティブなプロキシ状態を取得
            status = get_active_proxy_status()
            
            # 表示用メッセージを構築
            message_parts = []
            message_parts.append("=== 実際に適用されているプロキシ設定 ===\n")
            
            # プロキシモード
            mode = status.get('mode', 'UNKNOWN')
            message_parts.append(f"📌 プロキシモード: {mode}\n")
            
            # 実際のプロキシ辞書
            proxies = status.get('proxies', {})
            if proxies:
                message_parts.append("\n🌐 使用中のプロキシ:")
                for protocol, proxy_url in proxies.items():
                    message_parts.append(f"  • {protocol.upper()}: {proxy_url}")
            else:
                message_parts.append("\n🌐 使用中のプロキシ: なし (DIRECT接続)")
            
            # SSL証明書設定
            verify = status.get('verify', True)
            ca_bundle = status.get('ca_bundle', '')
            message_parts.append(f"\n\n🔒 SSL証明書検証: {'有効' if verify else '無効'}")
            message_parts.append(f"📄 CAバンドル: {ca_bundle}")
            
            # 環境変数信頼設定
            trust_env = status.get('trust_env', False)
            message_parts.append(f"\n🔧 環境変数信頼: {'有効' if trust_env else '無効'}")
            
            # 補足情報
            message_parts.append("\n\n💡 備考:")
            message_parts.append("このアプリケーションの全てのHTTP通信は、")
            message_parts.append("上記のプロキシ設定を使用します。")
            message_parts.append("WebViewはシステムプロキシを使用します。")
            
            message = "\n".join(message_parts)
            
            # メッセージボックスで表示
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("実際に適用されているプロキシ設定")
            msg_box.setText(message)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec_()
            
            # ログにも記録
            self.add_log("実際に適用されているプロキシ設定を表示しました")
            
        except Exception as e:
            error_msg = f"プロキシ状態取得エラー: {str(e)}"
            self.add_log(error_msg)
            QMessageBox.warning(self, "エラー", error_msg)
            logger.error(f"プロキシ状態表示エラー: {e}", exc_info=True)
            
    def apply_preset(self):
        """プリセット適用"""
        preset_name = self.preset_combo.currentData()
        if not preset_name:
            return
            
        try:
            from config.common import get_dynamic_file_path
            import yaml
            
            yaml_path = get_dynamic_file_path("config/network.yaml")
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    
                configurations = data.get('configurations', {})
                preset_config = configurations.get(preset_name, {})
                
                # プリセット設定をUIに適用
                mode = preset_config.get('mode', 'DIRECT').upper()
                
                if mode == 'DIRECT':
                    self.direct_radio.setChecked(True)
                elif mode == 'SYSTEM':
                    self.system_radio.setChecked(True)
                elif mode == 'HTTP':
                    self.http_radio.setChecked(True)
                    
                self.http_proxy_edit.setText(preset_config.get('http_proxy', ''))
                self.https_proxy_edit.setText(preset_config.get('https_proxy', ''))
                
                self.on_mode_changed()
                self.add_log(f"プリセット '{preset_name}' を適用しました")
                
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_error_message(f"プリセット適用エラー: {error_msg}", max_line_length=80)
            
            self.add_log(formatted_error)
            QMessageBox.warning(self, "エラー", formatted_error)
            
    def save_current_as_preset(self):
        """現在の設定をプリセットとして保存"""
        from qt_compat.widgets import QInputDialog
        
        preset_name, ok = QInputDialog.getText(self, "プリセット保存", "プリセット名を入力してください:")
        
        if ok and preset_name:
            try:
                config = self.get_current_ui_config()
                
                from config.common import get_dynamic_file_path
                import yaml
                
                yaml_path = get_dynamic_file_path("config/network.yaml")
                data = {}
                
                if os.path.exists(yaml_path):
                    with open(yaml_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f) or {}
                
                if 'configurations' not in data:
                    data['configurations'] = {}
                    
                data['configurations'][preset_name] = config
                
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(data, f, default_flow_style=False, 
                                 allow_unicode=True, sort_keys=False)
                
                self.load_presets()  # プリセット一覧を再読み込み
                self.add_log(f"プリセット '{preset_name}' を保存しました")
                QMessageBox.information(self, "保存完了", f"プリセット '{preset_name}' を保存しました")
                
            except Exception as e:
                error_msg = str(e)
                formatted_error = self._format_error_message(f"プリセット保存エラー: {error_msg}", max_line_length=80)
                
                self.add_log(formatted_error)
                QMessageBox.warning(self, "エラー", formatted_error)
                
    def run_connection_test(self):
        """接続テスト実行（4パターンの接続性評価）"""
        if self.test_worker and self.test_worker.isRunning():
            return
        
        # 既存のワーカーがある場合は完全にクリーンアップ
        if self.test_worker:
            try:
                self.test_worker.test_completed.disconnect()
                self.test_worker.progress_updated.disconnect()
            except:
                pass  # 未接続の場合は無視
            self.test_worker.deleteLater()
            self.test_worker = None
        
        # 現在のUI設定を取得
        config = self.get_current_ui_config()
        mode = config.get('mode', 'DIRECT').upper()
        
        # プロキシ情報を取得
        if mode == 'HTTP':
            # 手動プロキシ設定
            http_proxy = config.get('http_proxy', '')
            https_proxy = config.get('https_proxy', http_proxy)
            
            proxy_display = f"HTTP: {http_proxy}, HTTPS: {https_proxy}"
            
        elif mode == 'SYSTEM':
            # システムプロキシ使用
            try:
                from urllib.request import getproxies
                system_proxies = getproxies()
                http_proxy = system_proxies.get('http', '')
                https_proxy = system_proxies.get('https', http_proxy)
                proxy_display = f"システムプロキシ - HTTP: {http_proxy or 'なし'}, HTTPS: {https_proxy or 'なし'}"
            except Exception as e:
                self.add_log(f"❌ システムプロキシ取得エラー: {e}")
                return
                
        elif mode == 'DIRECT':
            # 直接接続
            proxy_display = "プロキシなし（直接接続）"
        else:
            proxy_display = f"モード: {mode}"
        
        # CA証明書設定を取得
        cert_config = config.get('cert', {})
        use_truststore = cert_config.get('enterprise_ca', {}).get('enable_truststore', False)
        custom_ca = cert_config.get('enterprise_ca', {}).get('custom_ca_bundle', '')
        
        # ヘッダパターンとカスタムヘッダを取得
        header_pattern = self.header_pattern_combo.currentData()
        custom_headers = {}
        if header_pattern == 'custom':
            try:
                import json
                custom_headers_text = self.custom_headers_edit.toPlainText().strip()
                if custom_headers_text:
                    custom_headers = json.loads(custom_headers_text)
            except json.JSONDecodeError as e:
                self.add_log(f"❌ カスタムヘッダのJSON解析エラー: {e}")
                QMessageBox.warning(self, "ヘッダエラー", f"カスタムヘッダのJSON形式が不正です:\n{e}")
                return
        
        self.test_button.setEnabled(False)
        self.test_webview_button.setEnabled(False)
        self.test_progress.setVisible(True)
        self.test_progress.setRange(0, 100)  # 0-100%のプログレスバー
        self.test_progress.setValue(0)
        
        # ヘッダパターン表示用
        from classes.config.conf.connection_test_headers import HEADER_PATTERNS
        header_pattern_name = HEADER_PATTERNS.get(header_pattern, {}).get('name', header_pattern)
        
        self.test_result_text.setPlainText(
            "🔄 接続テスト実行中（4パターンの接続性評価）...\n\n"
            f"【設定情報】\n"
            f"プロキシモード: {mode}\n"
            f"プロキシ詳細: {proxy_display}\n"
            f"truststore使用: {'有効' if use_truststore else '無効'}\n"
            f"カスタムCA: {custom_ca if custom_ca else 'なし'}\n"
            f"HTTPヘッダ: {header_pattern_name}\n"
            f"テストURL: https://rde.nims.go.jp/\n\n"
            "【テストパターン】\n"
            "1. 直接接続（プロキシなし）\n"
            "2. プロキシ経由（CA証明書なし・truststore不使用・SSL検証あり）\n"
            "3. プロキシ経由（CA証明書なし・truststore不使用・SSL検証なし）\n"
            "4. プロキシ経由（CA証明書あり・truststore使用・SSL検証あり）\n\n"
            "しばらくお待ちください..."
        )
        
        # テストワーカーに完全な設定を渡す
        self.test_worker = ProxyTestWorker(config, header_pattern, custom_headers)
        self.test_worker.test_completed.connect(self.on_test_completed)
        self.test_worker.progress_updated.connect(self.on_test_progress)
        self.test_worker.start()
        
        self.add_log(f"統合診断テスト開始: {proxy_display}")
    
    def on_test_progress(self, message: str, progress: int):
        """テスト進捗更新のコールバック"""
        self.test_progress.setValue(progress)
        # プログレスメッセージをログに記録
        self.add_log(f"[{progress}%] {message}")

    
    def run_webview_test(self):
        """WebView接続テスト実行（システムプロキシ設定を使用）"""
        try:
            from qt_compat.webengine import QWebEngineView, QWebEnginePage
            from qt_compat.core import QUrl
            import platform
            
            # 現在のUI設定を取得
            config = self.get_current_ui_config()
            mode = config.get('mode', 'DIRECT').upper()
            
            # 現在のシステムプロキシ状態を検出
            system_proxy_info = self._detect_system_proxy()
            
            # モードに応じた警告メッセージ
            mode_warning = ""
            if mode == 'HTTP':
                http_proxy = config.get('http_proxy', '')
                https_proxy = config.get('https_proxy', http_proxy)
                mode_warning = (
                    f"\n⚠️ 重要な注意:\n"
                    f"アプリ設定: HTTPモード ({http_proxy})\n"
                    f"しかし、WebViewはOSのシステムプロキシ設定を使用します。\n"
                    f"現在のシステムプロキシ: {system_proxy_info}\n\n"
                    f"HTTPモードで指定したプロキシを使用するには、\n"
                    f"OSのシステムプロキシ設定を同じ値に変更してください。\n"
                )
            elif mode == 'DIRECT':
                mode_warning = (
                    f"\n⚠️ 重要な注意:\n"
                    f"アプリ設定: DIRECTモード（プロキシなし）\n"
                    f"しかし、WebViewはOSのシステムプロキシ設定を使用します。\n"
                    f"現在のシステムプロキシ: {system_proxy_info}\n\n"
                    f"DIRECTモードでテストするには、\n"
                    f"OSのシステムプロキシ設定を無効にしてください。\n"
                )
            elif mode == 'SYSTEM':
                mode_warning = (
                    f"\n✅ SYSTEMモード:\n"
                    f"WebViewはOSのシステムプロキシ設定を使用します。\n"
                    f"現在のシステムプロキシ: {system_proxy_info}\n"
                )
            
            # テストウィンドウを作成（モーダルではなく情報表示のみ）
            self.test_result_text.setPlainText(
                "🔄 WebView接続テスト実行中...\n\n"
                f"【アプリ設定】\n"
                f"プロキシモード: {mode}\n"
                f"{mode_warning}\n"
                "【テスト情報】\n"
                f"テストURL: https://rde.nims.go.jp/\n\n"
                "💡 WebView制限事項:\n"
                "WebViewはQtWebEngineコンポーネントのため、\n"
                "常にOSのシステムプロキシ設定を使用します。\n"
                "アプリのプロキシ設定（HTTP/DIRECTモード）を反映するには、\n"
                "OSのシステムプロキシ設定を手動で変更する必要があります。"
            )
            
            # 3パターンのテスト結果を保存
            self._webview_test_results = {
                'direct': None,
                'proxy_no_ca': None,
                'proxy_with_ca': None,
                'current_test': 0
            }
            
            # 現在のテストパターンを決定（システムプロキシ設定から推測）
            if "プロキシなし" in system_proxy_info or "直接接続" in system_proxy_info:
                current_pattern = "direct"
                pattern_name = "直接接続（プロキシなし）"
            elif "localhost:8888" in system_proxy_info or "127.0.0.1:8888" in system_proxy_info:
                # Fiddlerの場合、CA証明書がインストールされているかチェック
                if self._check_fiddler_ca_installed():
                    current_pattern = "proxy_with_ca"
                    pattern_name = "プロキシ接続（CA証明書あり）"
                else:
                    current_pattern = "proxy_no_ca"
                    pattern_name = "プロキシ接続（CA証明書なし）"
            else:
                current_pattern = "proxy_with_ca"
                pattern_name = "プロキシ接続（システムプロキシ）"
            
            self._webview_test_results['current_test'] = current_pattern
            
            # WebViewを作成（インスタンス変数として保持）
            self._test_webview = QWebEngineView()
            self._test_completed = False  # 完了フラグ
            self._test_start_time = None
            
            # タイムアウトタイマー設定（15秒）
            self._test_timeout_timer = QTimer(self)
            self._test_timeout_timer.setSingleShot(True)
            
            def on_timeout():
                """タイムアウト処理"""
                if self._test_completed:
                    return
                    
                self._test_completed = True
                self._test_timeout_timer.stop()
                
                # 現在のパターンの結果を記録
                self._webview_test_results[current_pattern] = {
                    'success': False,
                    'message': 'タイムアウト',
                    'time': 15.0
                }
                
                result_text = self._format_webview_results(
                    current_pattern, pattern_name, system_proxy_info,
                    success=False, message="タイムアウト（15秒）"
                )
                self.test_result_text.setPlainText(result_text)
                self.add_log(f"WebViewテストタイムアウト [{pattern_name}]")
                
                # ダイアログを一度だけ表示
                QMessageBox.warning(self, "WebViewテスト", f"⏱️ タイムアウト（15秒）\n\nテストパターン: {pattern_name}")
                
                # WebViewをクリーンアップ
                self._cleanup_test_webview()
            
            def on_load_finished(success):
                """ページロード完了"""
                if self._test_completed:
                    return  # 既に処理済みの場合はスキップ
                
                self._test_completed = True
                self._test_timeout_timer.stop()  # タイムアウトタイマー停止
                
                # 応答時間計算
                import time
                elapsed = time.time() - self._test_start_time if self._test_start_time else 0
                
                # シグナルを切断して二重実行を防止
                try:
                    self._test_webview.loadFinished.disconnect(on_load_finished)
                except:
                    pass
                
                # 現在のパターンの結果を記録
                self._webview_test_results[current_pattern] = {
                    'success': success,
                    'message': '成功' if success else '失敗',
                    'time': elapsed
                }
                
                if success:
                    result_text = self._format_webview_results(
                        current_pattern, pattern_name, system_proxy_info,
                        success=True, message=f"成功 ({elapsed:.2f}秒)", elapsed=elapsed
                    )
                    self.test_result_text.setPlainText(result_text)
                    self.add_log(f"WebViewテスト成功 [{pattern_name}]")
                    
                    # ダイアログを一度だけ表示
                    QMessageBox.information(
                        self, "WebViewテスト", 
                        f"✅ WebView接続成功\n\nテストパターン: {pattern_name}\n応答時間: {elapsed:.2f}秒"
                    )
                else:
                    result_text = self._format_webview_results(
                        current_pattern, pattern_name, system_proxy_info,
                        success=False, message="接続失敗"
                    )
                    self.test_result_text.setPlainText(result_text)
                    self.add_log(f"WebViewテスト失敗 [{pattern_name}]")
                    
                    # ダイアログを一度だけ表示
                    QMessageBox.warning(
                        self, "WebViewテスト", 
                        f"❌ WebView接続失敗\n\nテストパターン: {pattern_name}"
                    )
                
                # WebViewをクリーンアップ
                QTimer.singleShot(1000, lambda: self._cleanup_test_webview())
            
            # タイムアウト設定
            self._test_timeout_timer.timeout.connect(on_timeout)
            self._test_timeout_timer.start(15000)  # 15秒
            
            # 開始時刻記録
            import time
            self._test_start_time = time.time()
            
            # シグナル接続
            self._test_webview.loadFinished.connect(on_load_finished)
            self._test_webview.load(QUrl("https://rde.nims.go.jp/"))
            
            self.add_log(f"WebViewテストを開始しました [{pattern_name}]")
            
        except Exception as e:
            self.add_log(f"WebViewテストエラー: {str(e)}")
            self.test_result_text.setPlainText(f"❌ WebViewテストエラー:\n{str(e)}")
            QMessageBox.critical(self, "エラー", f"WebViewテストでエラーが発生しました:\n{str(e)}")
    
    def run_integrated_diagnostics(self):
        """統合診断を実行（v2.2.0導入・v2.2.2検証済み）"""
        try:
            from classes.config.core.diagnostic_runner import DiagnosticRunner
            from classes.config.ui.diagnostic_result_dialog import DiagnosticResultDialog
            
            # 既存のランナーをクリーンアップ
            if hasattr(self, '_diagnostic_runner') and self._diagnostic_runner:
                try:
                    self._diagnostic_runner.cleanup()
                except:
                    pass
            
            # プログレスダイアログ表示
            self.test_button.setEnabled(False)
            self.test_webview_button.setEnabled(False)
            self.diagnostic_button.setEnabled(False)
            self.test_progress.setVisible(True)
            self.test_progress.setRange(0, 100)
            self.test_progress.setValue(0)
            
            self.test_result_text.setPlainText("🔍 統合診断実行中...\n診断には約1-2分かかります。しばらくお待ちください。")
            self.add_log("統合診断を開始しました")
            
            # 診断ランナー作成（インスタンス変数として保持）
            self._diagnostic_runner = DiagnosticRunner(parent_widget=self)
            
            # コールバック定義
            def on_completed(results):
                """診断完了時"""
                self.test_button.setEnabled(True)
                self.test_webview_button.setEnabled(True)
                self.diagnostic_button.setEnabled(True)
                self.test_progress.setVisible(False)
                
                # 結果サマリーを表示
                if results.get('success'):
                    passed = results.get('passed', 0)
                    total = results.get('total_tests', 0)
                    duration = results.get('duration', 0)
                    
                    # ゼロ除算を避ける
                    if total > 0:
                        percentage = passed / total * 100
                        summary = (
                            f"✅ 診断完了: {passed}/{total} 合格 ({percentage:.1f}%)\n"
                            f"所要時間: {duration:.1f}秒\n\n"
                            "詳細な結果をダイアログで表示します..."
                        )
                    else:
                        summary = (
                            f"⚠️ 診断完了: テスト結果なし\n"
                            f"所要時間: {duration:.1f}秒\n\n"
                            "詳細な結果をダイアログで表示します..."
                        )
                    
                    self.test_result_text.setPlainText(summary)
                    self.add_log(f"統合診断完了: {passed}/{total} 合格")
                    
                    # 結果ダイアログ表示
                    dialog = DiagnosticResultDialog(results, parent=self)
                    dialog.exec_()
                else:
                    error_msg = results.get('error', '不明なエラー')
                    self.test_result_text.setPlainText(f"❌ 診断失敗:\n{error_msg}")
                    self.add_log(f"統合診断失敗: {error_msg}")
                    QMessageBox.warning(self, "診断失敗", f"診断が失敗しました:\n{error_msg}")
            
            def on_error(error_message):
                """診断エラー時"""
                self.test_button.setEnabled(True)
                self.test_webview_button.setEnabled(True)
                self.diagnostic_button.setEnabled(True)
                self.test_progress.setVisible(False)
                
                self.test_result_text.setPlainText(f"❌ 診断エラー:\n{error_message}")
                self.add_log(f"統合診断エラー: {error_message}")
                QMessageBox.critical(self, "エラー", f"診断実行中にエラーが発生しました:\n{error_message}")
            
            def on_progress(message, percent):
                """プログレス更新時"""
                self.test_progress.setValue(percent)
                self.add_log(f"診断進捗: {message} ({percent}%)")
            
            # 診断実行（MitM環境を許可）
            self._diagnostic_runner.run_async(
                callback=on_completed,
                error_callback=on_error,
                progress_callback=on_progress,
                allow_mitm=True,
                verbose=False,
                timeout=300  # 5分
            )
            
        except ImportError as e:
            # 診断ツールが見つからない
            error_msg = f"診断ツールのインポートに失敗しました:\n{e}\n\n診断機能を使用するには、tests/proxy/ディレクトリに診断スクリプトが必要です。"
            self.test_result_text.setPlainText(f"❌ {error_msg}")
            self.add_log(f"診断ツールエラー: {e}")
            QMessageBox.critical(self, "エラー", error_msg)
        except Exception as e:
            # その他のエラー
            logger.exception("統合診断実行エラー")
            error_msg = f"診断実行中にエラーが発生しました:\n{e}"
            self.test_result_text.setPlainText(f"❌ {error_msg}")
            self.add_log(f"診断実行エラー: {e}")
            QMessageBox.critical(self, "エラー", error_msg)
    
    def _detect_system_proxy(self) -> str:
        """システムプロキシ設定を検出"""
        try:
            import platform
            import winreg
            
            if platform.system() == 'Windows':
                # Windowsレジストリからプロキシ設定を取得
                try:
                    key = winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
                    )
                    proxy_enable = winreg.QueryValueEx(key, "ProxyEnable")[0]
                    
                    if proxy_enable:
                        proxy_server = winreg.QueryValueEx(key, "ProxyServer")[0]
                        winreg.CloseKey(key)
                        return f"{proxy_server}"
                    else:
                        winreg.CloseKey(key)
                        return "プロキシなし（直接接続）"
                except:
                    return "不明（レジストリアクセスエラー）"
            else:
                # macOS/Linuxの場合は環境変数をチェック
                import os
                http_proxy = os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY')
                https_proxy = os.environ.get('https_proxy') or os.environ.get('HTTPS_PROXY')
                
                if https_proxy or http_proxy:
                    return f"{https_proxy or http_proxy}"
                else:
                    return "プロキシなし（直接接続）"
        except Exception as e:
            return f"検出失敗: {str(e)}"
    
    def _check_fiddler_ca_installed(self) -> bool:
        """FiddlerのCA証明書がインストールされているかチェック"""
        try:
            import platform
            import subprocess
            
            if platform.system() == 'Windows':
                # Windows証明書ストアをチェック
                # "DO_NOT_TRUST_FiddlerRoot" という名前の証明書を探す
                result = subprocess.run(
                    ['certutil', '-store', 'Root'],
                    capture_output=True, text=True, timeout=5
                )
                return 'FiddlerRoot' in result.stdout or 'Fiddler' in result.stdout
            else:
                # macOS/Linuxの場合は簡易チェック
                return False
        except:
            # エラーの場合は保守的に False を返す
            return False
    
    def _format_webview_results(self, current_pattern: str, pattern_name: str, 
                                 system_proxy_info: str, success: bool, 
                                 message: str, elapsed: float = 0) -> str:
        """WebViewテスト結果をフォーマット"""
        result_lines = ["=== WebView接続テスト結果 ===\n"]
        
        # 現在のテストパターン情報
        result_lines.append(f"【現在のテストパターン: {pattern_name}】")
        
        if success:
            result_lines.append(f"✅ WebView接続成功")
            result_lines.append(f"URL: https://rde.nims.go.jp/")
            result_lines.append(f"システムプロキシ: {system_proxy_info}")
            if elapsed > 0:
                result_lines.append(f"応答時間: {elapsed:.2f}秒")
        else:
            result_lines.append(f"❌ WebView接続失敗")
            result_lines.append(f"エラー: {message}")
            result_lines.append(f"URL: https://rde.nims.go.jp/")
            result_lines.append(f"システムプロキシ: {system_proxy_info}")
        
        result_lines.append("")
        result_lines.append("💡 3パターンテストについて:")
        result_lines.append("WebViewはOSのシステムプロキシ設定を使用するため、")
        result_lines.append("全パターンをテストするには以下の手順が必要です:")
        result_lines.append("")
        result_lines.append("【1. 直接接続テスト】")
        result_lines.append("  Windowsの設定 → ネットワークとインターネット")
        result_lines.append("  → プロキシ → プロキシサーバーを使う: OFF")
        result_lines.append("")
        result_lines.append("【2. プロキシ（CA証明書なし）テスト】")
        result_lines.append("  Fiddler起動 → Tools → Options → HTTPS")
        result_lines.append("  → Decrypt HTTPS traffic: OFF")
        result_lines.append("  → Actions → Trust Root Certificate: 削除")
        result_lines.append("")
        result_lines.append("【3. プロキシ（CA証明書あり）テスト】")
        result_lines.append("  Fiddler起動 → Tools → Options → HTTPS")
        result_lines.append("  → Decrypt HTTPS traffic: ON")
        result_lines.append("  → Actions → Trust Root Certificate")
        result_lines.append("")
        
        # 現在のテスト結果サマリー
        if hasattr(self, '_webview_test_results'):
            results = self._webview_test_results
            result_lines.append("【テスト実行状況】")
            
            direct = results.get('direct')
            if direct:
                status = "✅" if direct['success'] else "❌"
                result_lines.append(f"  直接接続: {status} {direct['message']}")
            else:
                result_lines.append(f"  直接接続: {'✅' if current_pattern == 'direct' and success else '⏹️ 未実施'}")
            
            proxy_no_ca = results.get('proxy_no_ca')
            if proxy_no_ca:
                status = "✅" if proxy_no_ca['success'] else "❌"
                result_lines.append(f"  プロキシ（CA無）: {status} {proxy_no_ca['message']}")
            else:
                result_lines.append(f"  プロキシ（CA無）: {'✅' if current_pattern == 'proxy_no_ca' and success else '⏹️ 未実施'}")
            
            proxy_with_ca = results.get('proxy_with_ca')
            if proxy_with_ca:
                status = "✅" if proxy_with_ca['success'] else "❌"
                result_lines.append(f"  プロキシ（CA有）: {status} {proxy_with_ca['message']}")
            else:
                result_lines.append(f"  プロキシ（CA有）: {'✅' if current_pattern == 'proxy_with_ca' and success else '⏹️ 未実施'}")
        
        return "\n".join(result_lines)
    
    def _cleanup_test_webview(self):
        """テスト用WebViewのクリーンアップ"""
        try:
            if hasattr(self, '_test_webview') and self._test_webview:
                # シグナルを切断（引数なしdisconnectは全スロット切断を試みるが、
                # 接続されていない場合に警告が出るため、try-exceptで無視）
                try:
                    # loadFinishedシグナルの全接続を切断
                    self._test_webview.loadFinished.disconnect()
                except (TypeError, RuntimeError):
                    # 接続されていない、または既に切断済みの場合は無視
                    pass
                    
                try:
                    self._test_webview.stop()
                except:
                    pass
                    
                self._test_webview.deleteLater()
                self._test_webview = None
                
            # タイムアウトタイマーもクリーンアップ
            if hasattr(self, '_test_timeout_timer') and self._test_timeout_timer:
                try:
                    self._test_timeout_timer.stop()
                except:
                    pass
                self._test_timeout_timer.deleteLater()
                self._test_timeout_timer = None
                
        except Exception as e:
            logger.debug(f"WebViewクリーンアップエラー: {e}")
    
    def on_test_completed(self, results: dict):
        """テスト完了時のコールバック（4パターンの接続性評価対応）"""
        self.test_button.setEnabled(True)
        self.test_webview_button.setEnabled(True)
        self.test_progress.setVisible(False)
        
        # 4パターンの結果を取得
        pattern1 = results.get('pattern1_direct', {})
        pattern2 = results.get('pattern2_proxy_no_ca_verify_on', {})
        pattern3 = results.get('pattern3_proxy_no_ca_verify_off', {})
        pattern4 = results.get('pattern4_proxy_with_ca', {})
        overall_success = results.get('overall_success', False)
        
        # 結果テキストを構築
        result_lines = ["=== 接続テスト結果（4パターンの接続性評価） ===\n"]
        
        # パターン1: 直接接続
        result_lines.append("【パターン1: 直接接続（プロキシなし）】")
        if pattern1.get('success'):
            result_lines.append(f"✅ {pattern1.get('message', '成功')}")
        else:
            result_lines.append(f"❌ {pattern1.get('message', '失敗')}")
        result_lines.append(pattern1.get('details', 'テスト未実施'))
        result_lines.append("")
        
        # パターン2: プロキシ経由（CA無・検証ON）
        result_lines.append("【パターン2: プロキシ経由（CA証明書なし・truststore不使用・SSL検証あり）】")
        if pattern2.get('success'):
            result_lines.append(f"✅ {pattern2.get('message', '成功')}")
        else:
            result_lines.append(f"❌ {pattern2.get('message', '失敗')}")
        result_lines.append(pattern2.get('details', 'テスト未実施'))
        result_lines.append("")
        
        # パターン3: プロキシ経由（CA無・検証OFF）
        result_lines.append("【パターン3: プロキシ経由（CA証明書なし・truststore不使用・SSL検証なし）】")
        if pattern3.get('success'):
            result_lines.append(f"⚠️ {pattern3.get('message', '成功')}")
        else:
            result_lines.append(f"❌ {pattern3.get('message', '失敗')}")
        result_lines.append(pattern3.get('details', 'テスト未実施'))
        result_lines.append("")
        
        # パターン4: プロキシ経由（CA有・truststore使用・検証ON）
        result_lines.append("【パターン4: プロキシ経由（CA証明書あり・truststore使用・SSL検証あり）】")
        if pattern4.get('success'):
            result_lines.append(f"✅ {pattern4.get('message', '成功')}")
        else:
            result_lines.append(f"❌ {pattern4.get('message', '失敗')}")
        result_lines.append(pattern4.get('details', 'テスト未実施'))
        result_lines.append("")
        
        # 推奨事項
        result_lines.append("【推奨設定】")
        if pattern1.get('success'):
            result_lines.append("✅ 直接接続が可能です（プロキシ不要な環境）")
        elif pattern4.get('success'):
            result_lines.append("✅ プロキシ + CA証明書で接続可能です（推奨設定）")
        elif pattern3.get('success') and not pattern2.get('success'):
            result_lines.append("⚠️ SSL検証を無効にすると接続できますが、セキュリティリスクがあります")
            result_lines.append("   → CA証明書のインストールを推奨します")
        else:
            result_lines.append("❌ すべてのパターンで接続失敗しました")
            result_lines.append("   → ネットワーク設定、プロキシ設定、CA証明書を確認してください")
        
        result_lines.append("")
        result_lines.append("【より詳細な診断】")
        result_lines.append("統合診断ボタン（🔍）で詳細な診断を実行できます")
        
        result_text = "\n".join(result_lines)
        self.test_result_text.setPlainText(result_text)
        
        # ログに記録
        success_count = sum([
            1 if pattern1.get('success') else 0,
            1 if pattern2.get('success') else 0,
            1 if pattern3.get('success') else 0,
            1 if pattern4.get('success') else 0
        ])
        self.add_log(f"接続テスト完了: {success_count}/4パターン成功")
        
        # 結果サマリー作成
        summary_lines = []
        if pattern1.get('success'):
            summary_lines.append(f"✅ 直接接続: {pattern1.get('message')}")
        else:
            summary_lines.append(f"❌ 直接接続: {pattern1.get('message')}")
        
        if pattern2.get('success'):
            summary_lines.append(f"✅ プロキシ(CA無/検証ON): {pattern2.get('message')}")
        else:
            summary_lines.append(f"❌ プロキシ(CA無/検証ON): {pattern2.get('message')}")
        
        if pattern3.get('success'):
            summary_lines.append(f"⚠️ プロキシ(CA無/検証OFF): {pattern3.get('message')}")
        else:
            summary_lines.append(f"❌ プロキシ(CA無/検証OFF): {pattern3.get('message')}")
        
        if pattern4.get('success'):
            summary_lines.append(f"✅ プロキシ(CA有): {pattern4.get('message')}")
        else:
            summary_lines.append(f"❌ プロキシ(CA有): {pattern4.get('message')}")
        
        summary = "\n".join(summary_lines)
        
        # 結果ダイアログ
        if overall_success:
            QMessageBox.information(
                self,
                "接続テスト完了",
                f"✅ {success_count}/4パターンで接続成功\n\n{summary}\n\n"
                "詳細はテスト結果欄を確認してください。"
            )
        else:
            QMessageBox.warning(
                self,
                "接続テスト失敗",
                f"❌ すべてのパターンで接続失敗\n\n{summary}\n\n"
                "詳細はテスト結果欄を確認してください。\n\n"
                "統合診断ボタン（🔍）でさらに詳しく診断できます。"
            )
        
        # ワーカーのクリーンアップ
        if self.test_worker:
            try:
                self.test_worker.test_completed.disconnect()
                self.test_worker.progress_updated.disconnect()
            except:
                pass  # 未接続の場合は無視
            self.test_worker.deleteLater()
            self.test_worker = None
            logger.debug("[接続テスト] ワーカークリーンアップ完了")
    
    def check_enterprise_ca_features(self):
        """組織内CA機能の利用可否確認"""
        try:
            features = []
            
            # pypac確認
            try:
                import pypac
                features.append("PAC自動設定")
            except ImportError:
                pass
                
            # truststore確認
            try:
                import truststore
                features.append("truststore")
            except ImportError:
                pass
                
            # wincertstore確認
            try:
                import wincertstore
                features.append("Windows証明書ストア")
            except ImportError:
                pass
                
            if features:
                status = f"利用可能機能: {', '.join(features)}"
                self.enterprise_ca_status_label.setStyleSheet("color: green; font-size: 10px;")
            else:
                status = "組織内CA機能は利用できません (パッケージ未インストール)"
                self.enterprise_ca_status_label.setStyleSheet("color: orange; font-size: 10px;")
                
            self.enterprise_ca_status_label.setText(status)
            
        except Exception as e:
            self.enterprise_ca_status_label.setText(f"機能確認エラー: {e}")
            self.enterprise_ca_status_label.setStyleSheet("color: red; font-size: 10px;")
            
    def test_pac_configuration(self):
        """PAC設定テスト"""
        try:
            import pypac
            
            self.add_log("PAC自動検出を開始...")
            
            # PAC検出
            pac = pypac.get_pac()
            if pac:
                self.add_log(f"✅ PAC検出成功: {pac}")
                
                # テスト用URLでプロキシ確認
                test_url = "https://www.google.com"
                proxy = pac.find_proxy_for_url(test_url, "www.google.com")
                self.add_log(f"テストURL ({test_url}) のプロキシ: {proxy}")
                
                QMessageBox.information(self, "PAC設定テスト", 
                                      f"PAC検出成功!\n\nPAC: {pac}\nテストプロキシ: {proxy}")
            else:
                self.add_log("⚠️ PAC検出失敗")
                QMessageBox.warning(self, "PAC設定テスト", 
                                  "PAC自動検出に失敗しました")
                
        except ImportError:
            QMessageBox.warning(self, "PAC設定テスト", 
                              "pypacパッケージがインストールされていません")
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_error_message(error_msg, max_line_length=80)
            
            self.add_log(f"❌ PAC設定テストエラー: {formatted_error}")
            QMessageBox.critical(self, "PAC設定テスト", 
                               f"PAC設定テストでエラーが発生しました:\n\n{formatted_error}")
            
    def test_enterprise_ca(self):
        """組織内CA確認テスト"""
        try:
            info_lines = []
            
            # certifi標準バンドル
            try:
                import certifi
                standard_bundle = certifi.where()
                standard_size = os.path.getsize(standard_bundle)
                info_lines.append(f"標準certifiバンドル:")
                info_lines.append(f"  パス: {standard_bundle}")
                info_lines.append(f"  サイズ: {standard_size:,} bytes")
            except Exception as e:
                info_lines.append(f"標準certifiバンドル: エラー - {e}")
                
            # truststore証明書バンドル
            try:
                import truststore
                info_lines.append(f"truststore:")
                info_lines.append(f"  バージョン: {truststore.__version__}")
                info_lines.append(f"  SSL強化: 利用可能")
            except ImportError:
                info_lines.append("truststore: 利用不可 (truststore未インストール)")
            except Exception as e:
                info_lines.append(f"truststore: エラー - {e}")
                
            # Windows証明書ストア
            try:
                import wincertstore
                ca_store = wincertstore.CertSystemStore('CA')
                root_store = wincertstore.CertSystemStore('ROOT')
                
                ca_count = len(list(ca_store.itercerts()))
                root_count = len(list(root_store.itercerts()))
                
                info_lines.append(f"Windows証明書ストア:")
                info_lines.append(f"  CA証明書: {ca_count}件")
                info_lines.append(f"  ROOT証明書: {root_count}件")
            except ImportError:
                info_lines.append("Windows証明書ストア: 利用不可 (wincertstore未インストール)")
            except Exception as e:
                info_lines.append(f"Windows証明書ストア: エラー - {e}")
                
            # 現在のセッションマネージャ設定
            try:
                from net.session_manager import ProxySessionManager
                manager = ProxySessionManager()
                current_verify = getattr(manager.get_session(), 'verify', 'なし')
                info_lines.append(f"現在のSSL検証設定: {current_verify}")
            except Exception as e:
                info_lines.append(f"現在のセッション情報: エラー - {e}")
                
            info_text = "\n".join(info_lines)
            
            # ログにも出力
            for line in info_lines:
                self.add_log(line)
                
            QMessageBox.information(self, "組織内CA確認", 
                                  f"組織内CA情報:\n\n{info_text}")
            
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_error_message(error_msg, max_line_length=80)
            
            full_error_msg = f"組織内CA確認でエラーが発生しました:\n\n{formatted_error}"
            self.add_log(f"❌ 組織内CA確認エラー: {formatted_error}")
            QMessageBox.critical(self, "組織内CA確認", full_error_msg)
            
    def update_ui_from_config(self):
        """設定からUIを更新 (企業CA設定含む) - ファイル読み込み時やプリセット適用時に使用"""
        mode = self.current_config.get('mode', 'DIRECT').upper()
        
        # ログ出力で呼び出し元を明確化
        self.add_log(f"🔄 UI更新開始 - 設定ファイルからUI入力欄を更新: {mode}")
        
        # 現在の状態表示を更新
        self.current_mode_label.setText(mode)
        
        # プロキシ情報表示
        if mode == 'SYSTEM':
            try:
                from urllib.request import getproxies
                system_proxies = getproxies()
                http_proxy = system_proxies.get('http', 'なし')
                https_proxy = system_proxies.get('https', 'なし')
            except:
                http_proxy = 'システム設定取得エラー'
                https_proxy = 'システム設定取得エラー'
        else:
            proxies_config = self.current_config.get('proxies', {})
            http_proxy = (self.current_config.get('http_proxy') or 
                         proxies_config.get('http', 'なし'))
            https_proxy = (self.current_config.get('https_proxy') or 
                          proxies_config.get('https', 'なし'))
        
        self.current_http_proxy_label.setText(http_proxy)
        self.current_https_proxy_label.setText(https_proxy)
        
        # SSL証明書状態を更新
        self.update_ssl_certificate_status()
        self.update_ssl_certificate_details()
        
        # モードラジオボタン設定
        if mode == 'DIRECT':
            self.direct_radio.setChecked(True)
        elif mode == 'SYSTEM':
            self.system_radio.setChecked(True)
        elif mode == 'HTTP':
            self.http_radio.setChecked(True)
        elif mode == 'PAC':
            self.pac_radio.setChecked(True)
            
        # プロキシ詳細設定
        self.http_proxy_edit.setText(self.current_config.get('http_proxy', ''))
        self.https_proxy_edit.setText(self.current_config.get('https_proxy', ''))
        self.no_proxy_edit.setText(self.current_config.get('no_proxy', ''))
        
        # 企業CA設定の更新
        self.update_enterprise_ca_ui()
        
        # 除外リスト
        no_proxy = self.current_config.get('no_proxy', '')
        self.no_proxy_edit.setText(no_proxy)
        
        self.on_mode_changed()
        
    def update_enterprise_ca_ui(self):
        """企業CA設定UIの更新"""
        try:
            cert_config = self.current_config.get('cert', {})
            enterprise_ca = cert_config.get('enterprise_ca', {})
            pac_config = self.current_config.get('pac', {})
            
            # PAC設定
            self.pac_auto_detect_checkbox.setChecked(pac_config.get('auto_detect', False))
            self.pac_fallback_checkbox.setChecked(pac_config.get('fallback_to_system', True))
            
            # 企業CA設定
            self.enable_truststore_checkbox.setChecked(enterprise_ca.get('enable_truststore', False))
            self.auto_detect_corporate_ca_checkbox.setChecked(enterprise_ca.get('auto_detect_corporate_ca', False))
            self.custom_ca_bundle_edit.setText(enterprise_ca.get('custom_ca_bundle', ''))
            
            # SSL戦略設定
            proxy_ssl = cert_config.get('proxy_ssl_handling', {})
            strategy = proxy_ssl.get('strategy', 'use_proxy_ca')
            
            strategy_index = 0
            if strategy == 'strict_verification':
                strategy_index = 1
            elif strategy == 'fallback_no_verify':
                strategy_index = 2
                
            self.ssl_strategy_combo.setCurrentIndex(strategy_index)
            
        except Exception as e:
            self.add_log(f"企業CA UI更新エラー: {e}")
            
    def update_current_status_display(self):
        """現在の状態表示のみを更新（入力フィールドは変更しない）- OS設定も更新"""
        try:
            mode = self.current_config.get('mode', 'DIRECT').upper()
            
            # ========== アプリケーション設定の表示を更新 ==========
            self.current_mode_label.setText(mode)
            
            # プロキシ情報表示
            if mode == 'SYSTEM':
                try:
                    from urllib.request import getproxies
                    system_proxies = getproxies()
                    http_proxy = system_proxies.get('http', 'なし')
                    https_proxy = system_proxies.get('https', 'なし')
                except:
                    http_proxy = 'システム設定取得エラー'
                    https_proxy = 'システム設定取得エラー'
            else:
                proxies_config = self.current_config.get('proxies', {})
                http_proxy = (self.current_config.get('http_proxy') or 
                            proxies_config.get('http', 'なし'))
                https_proxy = (self.current_config.get('https_proxy') or 
                             proxies_config.get('https', 'なし'))
            
            self.current_http_proxy_label.setText(http_proxy)
            self.current_https_proxy_label.setText(https_proxy)
            
            # 環境変数信頼設定を表示
            try:
                from net.session_manager import get_active_proxy_status
                status = get_active_proxy_status()
                trust_env = status.get('trust_env', False)
                trust_env_text = "有効" if trust_env else "無効"
                trust_env_style = "color: green; font-weight: bold;" if trust_env else "color: gray;"
                self.current_trust_env_label.setText(trust_env_text)
                self.current_trust_env_label.setStyleSheet(trust_env_style)
            except Exception as e:
                self.current_trust_env_label.setText("取得エラー")
                logger.error(f"trust_env取得エラー: {e}")
            
            # SSL証明書状態を更新
            self.update_ssl_certificate_status()
            self.update_ssl_certificate_details()
            
            # ========== OS/システム設定の表示を更新 ==========
            self._update_os_proxy_status()
            
        except Exception as e:
            self.add_log(f"状態表示更新エラー: {e}")
            logger.error(f"状態表示更新エラー: {e}")
    
    def _update_os_proxy_status(self):
        """OS/システムのプロキシ設定を取得して表示"""
        try:
            # OSのシステムプロキシ設定を取得
            from urllib.request import getproxies
            system_proxies = getproxies()
            
            os_http = system_proxies.get('http', 'なし')
            os_https = system_proxies.get('https', 'なし')
            
            self.os_http_proxy_label.setText(os_http)
            self.os_https_proxy_label.setText(os_https)
            
            # 環境変数から取得
            import os as os_module
            env_http = os_module.environ.get('HTTP_PROXY') or os_module.environ.get('http_proxy', 'なし')
            env_https = os_module.environ.get('HTTPS_PROXY') or os_module.environ.get('https_proxy', 'なし')
            
            self.env_http_proxy_label.setText(env_http)
            self.env_https_proxy_label.setText(env_https)
            
            # アプリ設定とOS設定が異なる場合に警告表示
            app_mode = self.current_config.get('mode', 'DIRECT').upper()
            
            if app_mode == 'DIRECT' and (os_http != 'なし' or env_http != 'なし'):
                # DIRECTモードだがOS/環境変数にプロキシ設定あり
                self.os_http_proxy_label.setStyleSheet("color: orange; font-weight: bold;")
                self.os_http_proxy_label.setToolTip(
                    "⚠️ アプリは DIRECT モードですが、OSにプロキシ設定があります。\n"
                    "アプリはこの設定を無視して直接接続します。"
                )
            elif app_mode == 'SYSTEM':
                # SYSTEMモード - OS設定を使用することを明示
                self.os_http_proxy_label.setStyleSheet("color: green; font-weight: bold;")
                self.os_http_proxy_label.setToolTip("✅ アプリはこのOS設定を使用しています。")
                self.os_https_proxy_label.setStyleSheet("color: green; font-weight: bold;")
                self.os_https_proxy_label.setToolTip("✅ アプリはこのOS設定を使用しています。")
            else:
                # 通常表示
                self.os_http_proxy_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
                self.os_http_proxy_label.setToolTip("")
                self.os_https_proxy_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
                self.os_https_proxy_label.setToolTip("")
            
        except Exception as e:
            self.os_http_proxy_label.setText(f"取得エラー: {e}")
            self.os_https_proxy_label.setText(f"取得エラー: {e}")
            self.env_http_proxy_label.setText(f"取得エラー: {e}")
            self.env_https_proxy_label.setText(f"取得エラー: {e}")
            logger.error(f"OS/システムプロキシ取得エラー: {e}")
            
    def get_current_ui_config(self):
        """現在のUI設定から設定辞書を取得 (企業CA設定含む)"""
        config = {}
        
        # 基本プロキシ設定
        if self.direct_radio.isChecked():
            config['mode'] = 'DIRECT'
        elif self.system_radio.isChecked():
            config['mode'] = 'SYSTEM'
        elif self.http_radio.isChecked():
            config['mode'] = 'HTTP'
            config['http_proxy'] = self.http_proxy_edit.text()
            config['https_proxy'] = self.https_proxy_edit.text()
        elif self.pac_radio.isChecked():
            config['mode'] = 'PAC'
            
        config['no_proxy'] = self.no_proxy_edit.text()
        
        # 企業CA設定の追加
        if hasattr(self, 'pac_auto_detect_checkbox'):
            config['pac'] = {
                'auto_detect': self.pac_auto_detect_checkbox.isChecked(),
                'fallback_to_system': self.pac_fallback_checkbox.isChecked(),
                'timeout': 10
            }
            
            # SSL戦略
            strategy_map = {
                0: 'use_proxy_ca',
                1: 'strict_verification', 
                2: 'fallback_no_verify'
            }
            
            config['cert'] = {
                'verify': True,
                'enterprise_ca': {
                    'enable_truststore': self.enable_truststore_checkbox.isChecked(),
                    'auto_detect_corporate_ca': self.auto_detect_corporate_ca_checkbox.isChecked(),
                    'custom_ca_bundle': self.custom_ca_bundle_edit.text()
                },
                'proxy_ssl_handling': {
                    'strategy': strategy_map.get(self.ssl_strategy_combo.currentIndex(), 'use_proxy_ca'),
                    'fallback_to_no_verify': True,
                    'log_ssl_errors': True
                }
            }
            
        return config
    
    def apply_fiddler_quick_config(self):
        """Fiddler用の簡易設定を適用"""
        try:
            # HTTPプロキシモードに設定
            self.http_radio.setChecked(True)
            
            # プロキシアドレス設定
            self.http_proxy_edit.setText("http://localhost:8888")
            self.https_proxy_edit.setText("http://localhost:8888")
            
            # OS証明書ストア使用を有効化（これがSSL検証有効化の代わり）
            self.enable_truststore_checkbox.setChecked(True)
            
            # SSL戦略を use_proxy_ca に設定（企業CA対応）
            self.ssl_strategy_combo.setCurrentIndex(0)  # use_proxy_ca
            
            self.add_log("✅ Fiddler用設定を適用しました")
            self.add_log("   プロキシ: http://localhost:8888")
            self.add_log("   OS証明書ストア使用: 有効")
            self.add_log("   SSL戦略: use_proxy_ca")
            
            QMessageBox.information(
                self,
                "設定適用",
                "✅ Fiddler用設定を適用しました\n\n"
                "プロキシ: http://localhost:8888\n"
                "OS証明書ストア使用: 有効\n"
                "SSL戦略: use_proxy_ca\n\n"
                "「設定を適用」ボタンで保存してください。"
            )
            
        except Exception as e:
            error_msg = f"Fiddler設定適用エラー: {str(e)}"
            self.add_log(f"❌ {error_msg}")
            QMessageBox.warning(self, "エラー", error_msg)
    
    def apply_direct_quick_config(self):
        """プロキシなし（直接接続）の簡易設定を適用"""
        try:
            # DIRECTモードに設定
            self.direct_radio.setChecked(True)
            
            # プロキシアドレスをクリア
            self.http_proxy_edit.clear()
            self.https_proxy_edit.clear()
            
            self.add_log("✅ プロキシなし設定を適用しました")
            self.add_log("   モード: DIRECT（直接接続）")
            
            QMessageBox.information(
                self,
                "設定適用",
                "✅ プロキシなし設定を適用しました\n\n"
                "モード: DIRECT（直接接続）\n\n"
                "「設定を適用」ボタンで保存してください。"
            )
            
        except Exception as e:
            error_msg = f"直接接続設定適用エラー: {str(e)}"
            self.add_log(f"❌ {error_msg}")
            QMessageBox.warning(self, "エラー", error_msg)
    
    def apply_no_ssl_quick_config(self):
        """プロキシあり・SSL検証無効の簡易設定を適用"""
        try:
            # 現在のプロキシ設定を維持
            # SSL戦略を disable_verify に設定するために、
            # まず現在の設定を確認
            current_mode = None
            if self.direct_radio.isChecked():
                current_mode = "DIRECT"
            elif self.system_radio.isChecked():
                current_mode = "SYSTEM"
            elif self.http_radio.isChecked():
                current_mode = "HTTP"
            
            if current_mode in ["DIRECT", "SYSTEM"]:
                # プロキシがない場合は警告
                QMessageBox.warning(
                    self,
                    "注意",
                    "現在プロキシが設定されていません。\n"
                    "先にプロキシを設定してください。"
                )
                return
            
            # SSL証明書ストア使用を無効化
            self.enable_truststore_checkbox.setChecked(False)
            
            self.add_log("⚠️ SSL検証無効設定を適用しました")
            self.add_log("   現在のプロキシ設定を維持")
            self.add_log("   OS証明書ストア使用: 無効")
            
            QMessageBox.warning(
                self,
                "設定適用",
                "⚠️ SSL検証関連設定を変更しました\n\n"
                "現在のプロキシ設定を維持\n"
                "OS証明書ストア使用: 無効\n\n"
                "注意: セキュリティリスクがあります。\n"
                "テスト環境でのみ使用してください。\n\n"
                "「設定を適用」ボタンで保存してください。"
            )
            
        except Exception as e:
            error_msg = f"SSL無効設定適用エラー: {str(e)}"
            self.add_log(f"❌ {error_msg}")
            QMessageBox.warning(self, "エラー", error_msg)
        
    def apply_settings(self):
        """設定を適用"""
        try:
            config = self.get_current_ui_config()
            
            # デバッグ：適用しようとしている設定をログに出力
            mode = config.get('mode', 'UNKNOWN')
            self.add_log(f"🔧 設定適用開始 - モード: {mode}")
            
            if mode == 'HTTP':
                http_proxy = config.get('http_proxy', '')
                https_proxy = config.get('https_proxy', '')
                self.add_log(f"📋 手動プロキシ設定:")
                self.add_log(f"   HTTP: {http_proxy}")
                self.add_log(f"   HTTPS: {https_proxy}")
            
            # 設定変更を検出
            settings_changed = self._detect_settings_change(config)
            
            from net.session_manager import ProxySessionManager
            manager = ProxySessionManager()
            manager.configure(config)
            
            # 設定ファイルに完全に保存（network セクションとトップレベル両方）
            from config.common import get_dynamic_file_path
            import yaml
            
            yaml_path = get_dynamic_file_path("config/network.yaml")
            data = {}
            
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
            
            # network セクションが存在しなければ作成
            if 'network' not in data:
                data['network'] = {}
            
            # network セクション内のプロキシ設定を更新
            data['network']['mode'] = config.get('mode', 'DIRECT')
            
            # プロキシ詳細設定を保存
            if 'proxies' not in data['network']:
                data['network']['proxies'] = {}
                
            if mode == 'HTTP':
                http_proxy = config.get('http_proxy', '')
                https_proxy = config.get('https_proxy', '')
                data['network']['proxies']['http'] = http_proxy
                data['network']['proxies']['https'] = https_proxy
                self.add_log(f"💾 ファイル保存 (network.proxies) - HTTP: {http_proxy}")
                self.add_log(f"💾 ファイル保存 (network.proxies) - HTTPS: {https_proxy}")
            elif mode == 'SYSTEM':
                # SYSTEM モードの場合は proxies を空にする
                data['network']['proxies'] = {}
                self.add_log(f"💾 ファイル保存 - システムプロキシを使用")
            elif mode == 'DIRECT':
                # DIRECT モードの場合は proxies を空にする
                data['network']['proxies'] = {}
                self.add_log(f"💾 ファイル保存 - プロキシなし（直接接続）")
            
            # no_proxy設定
            if 'no_proxy' in config:
                data['network']['proxies']['no_proxy'] = config['no_proxy']
            
            # 企業CA設定を保存
            if 'cert' in config:
                data['network']['cert'] = config['cert']
            
            if 'pac' in config:
                data['network']['pac'] = config['pac']
            
            # トップレベルの設定も同期（後方互換性のため）
            data['mode'] = config.get('mode', 'DIRECT')
            if mode == 'HTTP' and 'http_proxy' in config:
                data['http_proxy'] = config['http_proxy']
                data['https_proxy'] = config.get('https_proxy', config['http_proxy'])
            else:
                # DIRECT/SYSTEM モードではトップレベルのプロキシ設定をクリア
                data.pop('http_proxy', None)
                data.pop('https_proxy', None)
                
            # YAMLファイルに保存
            with open(yaml_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, default_flow_style=False, 
                             allow_unicode=True, sort_keys=False)
            
            self.add_log(f"✅ 設定ファイルを保存しました: {yaml_path}")
            
            # 現在の設定を保存済みの設定で更新（UIは保持）
            self.current_config = config.copy()
            
            # 現在の状態表示のみを更新（入力フィールドは変更しない）
            self.update_current_status_display()
            
            self.add_log("✅ 設定を適用しました")
            
            # 設定が変更された場合は再起動を促す
            if settings_changed:
                self._prompt_restart()
            else:
                QMessageBox.information(self, "設定適用", "プロキシ設定を適用しました")
            
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_error_message(f"設定適用エラー: {error_msg}", max_line_length=80)
            
            self.add_log(formatted_error)
            QMessageBox.warning(self, "エラー", formatted_error)
    
    def _detect_settings_change(self, new_config: dict) -> bool:
        """
        プロキシ設定の変更を検出
        
        Args:
            new_config: 新しい設定
            
        Returns:
            bool: 設定が変更された場合True
        """
        if not hasattr(self, 'current_config') or not self.current_config:
            # 初回設定の場合は変更とみなさない
            return False
        
        # 重要な設定項目を比較
        important_keys = ['mode', 'http_proxy', 'https_proxy']
        
        for key in important_keys:
            old_value = self.current_config.get(key, '')
            new_value = new_config.get(key, '')
            
            # 値が変更された場合
            if old_value != new_value:
                self.add_log(f"⚠️  設定変更検出: {key} ({old_value} → {new_value})")
                return True
        
        return False
    
    def _prompt_restart(self):
        """プロキシ設定変更時の終了プロンプト（再起動なし）"""
        from qt_compat.widgets import QMessageBox
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("プロキシ設定変更 - 再起動が必要")
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText(
            "プロキシ設定を変更しました。\n\n"
            "変更を完全に適用するには、アプリケーションの再起動が必要です。"
        )
        msg_box.setInformativeText(
            "【重要】\n"
            "「終了する」をクリックするとアプリケーションを終了します。\n"
            "終了後、再度アプリケーションを起動してください。"
        )
        msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg_box.setDefaultButton(QMessageBox.Ok)
        
        # ボタンのテキストをカスタマイズ
        ok_button = msg_box.button(QMessageBox.Ok)
        ok_button.setText("終了する")
        
        cancel_button = msg_box.button(QMessageBox.Cancel)
        cancel_button.setText("キャンセル（後で再起動）")
        
        result = msg_box.exec_()
        
        if result == QMessageBox.Ok:
            self.add_log("🔄 アプリケーションを終了します。再度起動してください。")
            self._close_application()
        else:
            self.add_log("⚠️  後で手動で再起動してください。変更を適用するには再起動が必要です。")
            
            # キャンセルした場合の注意喚起
            QMessageBox.information(
                self,
                "再起動リマインダー",
                "プロキシ設定の変更を完全に適用するには、\n"
                "アプリケーションを手動で再起動してください。\n\n"
                "再起動するまで、古い設定が使用される可能性があります。"
            )
    
    def _close_application(self):
        """アプリケーションを終了（再起動なし）"""
        try:
            from qt_compat.core import QCoreApplication
            
            self.add_log("📝 設定を保存しました。")
            self.add_log("🔄 アプリケーションを終了します...")
            self.add_log("✅ 終了後、再度アプリケーションを起動してください。")
            
            # 最終確認メッセージ
            QMessageBox.information(
                self,
                "アプリケーション終了",
                "設定を保存しました。\n\n"
                "アプリケーションを終了します。\n"
                "再度起動して、新しい設定を適用してください。"
            )
            
            # アプリケーションを終了
            QCoreApplication.quit()
            
        except Exception as e:
            self.add_log(f"❌ 終了エラー: {e}")
            QMessageBox.critical(
                self,
                "終了エラー",
                f"アプリケーションの終了処理でエラーが発生しました。\n\n"
                f"エラー: {e}\n\n"
                "手動でアプリケーションを終了してください。"
            )
            
    def reset_to_defaults(self):
        """デフォルト設定に戻す"""
        reply = QMessageBox.question(self, "デフォルトに戻す",
                                   "プロキシ設定をデフォルト（DIRECT）に戻しますか？",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.direct_radio.setChecked(True)
            self.http_proxy_edit.clear()
            self.https_proxy_edit.clear()
            self.no_proxy_edit.setText("localhost,127.0.0.1,.local")
            self.on_mode_changed()
            self.add_log("設定をデフォルトに戻しました")
            
    def clear_log(self):
        """ログクリア"""
        self.log_text.clear()
        
    def add_log(self, message: str):
        """ログメッセージ追加"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
        # 自動スクロール
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
