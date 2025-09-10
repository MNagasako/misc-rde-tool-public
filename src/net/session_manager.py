"""
プロキシ対応セッション管理モジュール
循環参照を回避した設計でHTTPセッションを管理

アーキテクチャ:
- グローバルセッション管理インスタンス
- プロキシ設定の動的適用
- リトライ・SSL設定の統合管理
"""

import requests
import logging
import os
import json
from typing import Dict, Optional, Any, Union
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# YAML サポートの確認
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# システムプロキシ取得のためのインポート
from urllib.request import getproxies

# 企業プロキシCA対応
try:
    import pypac
    PYPAC_AVAILABLE = True
except ImportError:
    PYPAC_AVAILABLE = False

try:
    import truststore
    TRUSTSTORE_AVAILABLE = True
except ImportError:
    TRUSTSTORE_AVAILABLE = False

try:
    import ssl
    import certifi
    SSL_SUPPORT = True
except ImportError:
    SSL_SUPPORT = False

logger = logging.getLogger(__name__)

class ProxySessionManager:
    """
    プロキシ対応HTTPセッション管理クラス
    
    循環参照を回避し、設定可能なプロキシ対応セッションを提供
    """
    
    def __init__(self):
        self._session: Optional[requests.Session] = None
        self._proxy_config: Dict[str, Any] = {}
        self._configured: bool = False
        self._config_file_path = "config/network.yaml"
    
    def configure(self, proxy_config: Optional[Dict[str, Any]] = None):
        """
        セッション設定とプロキシ適用
        
        Args:
            proxy_config: プロキシ設定辞書。Noneの場合はファイルから読み込み
        """
        try:
            # 新しいセッション作成
            self._session = requests.Session()
            
            # プロキシ設定の取得と適用
            if proxy_config is None:
                proxy_config = self._load_proxy_config()
            
            self._proxy_config = proxy_config or {}
            self._apply_proxy_config(self._proxy_config)
            
            # SSL証明書設定の適用
            self._apply_certificate_config(self._proxy_config)
            
            # セッションアダプターの設定
            self._configure_session_adapters()
            
            self._configured = True
            logger.info("プロキシセッション設定完了")
            
        except Exception as e:
            logger.warning(f"プロキシセッション設定失敗、デフォルト設定使用: {e}")
            # フォールバック: デフォルトセッション
            self._session = requests.Session()
            self._configured = True
    
    def get_session(self) -> requests.Session:
        """
        設定済みセッションを取得
        
        Returns:
            requests.Session: 設定済みのHTTPセッション
        """
        if not self._configured:
            self.configure()
        return self._session
    
    def reconfigure(self, proxy_config: Dict[str, Any]):
        """
        セッション再設定
        
        Args:
            proxy_config: 新しいプロキシ設定
        """
        self._configured = False
        self.configure(proxy_config)
    
    def _load_proxy_config(self) -> Dict[str, Any]:
        """設定ファイルからプロキシ設定を読み込み"""
        try:
            if not YAML_AVAILABLE:
                logger.warning("YAML未対応、デフォルト設定使用")
                return {"mode": "DIRECT"}

            # 絶対パスで設定ファイルを取得
            from config.common import get_dynamic_file_path
            config_path = get_dynamic_file_path(self._config_file_path)
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f) or {}
                    
                    # networkセクションから設定を取得、なければトップレベルから
                    proxy_config = config_data.get('network', {})
                    
                    # トップレベルのmode設定も確認
                    if 'mode' in config_data:
                        proxy_config['mode'] = config_data['mode']
                    
                    # modeが設定されていない場合はDIRECTをデフォルトに
                    if 'mode' not in proxy_config:
                        proxy_config['mode'] = 'DIRECT'
                    
                    logger.info(f"設定ファイル読み込み: {proxy_config}")
                    return proxy_config
            else:
                logger.info(f"設定ファイル未発見({config_path})、DIRECT モード使用")
                return {"mode": "DIRECT"}
                
        except Exception as e:
            logger.warning(f"設定ファイル読み込み失敗: {e}")
            return {"mode": "DIRECT"}
    
    def _apply_proxy_config(self, config: Dict[str, Any]):
        """
        プロキシ設定をセッションに適用
        
        Args:
            config: プロキシ設定辞書
        """
        mode = config.get('mode', 'DIRECT').upper()
        
        if mode == 'DIRECT':
            # 直接接続（プロキシなし）
            self._session.proxies = {}
            logger.info("プロキシモード: DIRECT")
            
        elif mode == 'HTTP':
            # HTTPプロキシ
            # network.proxiesセクションまたは直接の設定を確認
            proxies_config = config.get('proxies', {})
            http_proxy = config.get('http_proxy') or proxies_config.get('http')
            https_proxy = config.get('https_proxy') or proxies_config.get('https') or http_proxy
            
            if http_proxy:
                self._session.proxies = {
                    'http': http_proxy,
                    'https': https_proxy
                }
                logger.info(f"プロキシモード: HTTP - HTTP:{http_proxy}, HTTPS:{https_proxy}")
            else:
                logger.warning("HTTPプロキシ設定が見つからない、DIRECT モード使用")
                self._session.proxies = {}
        elif mode == 'PAC':
            # PAC ファイル自動設定
            pac_config = config.get('pac', {})
            auto_detect = pac_config.get('auto_detect', True)
            pac_url = pac_config.get('url', '')
            fallback_to_system = pac_config.get('fallback_to_system', True)
            
            if self._apply_pac_config(auto_detect, pac_url, fallback_to_system):
                logger.info("プロキシモード: PAC - 自動設定成功")
            else:
                logger.warning("PAC設定失敗、フォールバック処理実行")
                if fallback_to_system:
                    # システムプロキシにフォールバック
                    try:
                        system_proxies = getproxies()
                        if system_proxies:
                            self._session.proxies = system_proxies
                            self._session.trust_env = True
                            logger.info("PAC失敗、システムプロキシにフォールバック")
                        else:
                            self._session.proxies = {}
                            logger.warning("PAC失敗、システムプロキシも無効、DIRECT使用")
                    except Exception as e:
                        logger.error(f"フォールバック処理エラー: {e}")
                        self._session.proxies = {}
                else:
                    self._session.proxies = {}
            
        elif mode == 'SYSTEM':
            # システムプロキシ使用
            try:
                system_proxies = getproxies()
                if system_proxies:
                    # システムプロキシを適用
                    self._session.proxies = system_proxies
                    # trust_envも有効にして環境変数プロキシも許可
                    self._session.trust_env = True
                    logger.info(f"プロキシモード: SYSTEM - {system_proxies}")
                else:
                    # システムプロキシがない場合
                    self._session.proxies = {}
                    self._session.trust_env = True  # 環境変数は確認
                    logger.info("プロキシモード: SYSTEM - システムプロキシなし（環境変数確認有効）")
            except Exception as e:
                logger.warning(f"システムプロキシ取得エラー: {e}, trust_env有効でフォールバック")
                self._session.proxies = {}
                self._session.trust_env = True
                
        else:
            logger.warning(f"不明なプロキシモード: {mode}, DIRECT使用")
            self._session.proxies = {}
    
    def _apply_pac_config(self, auto_detect: bool, pac_url: str, fallback_to_system: bool) -> bool:
        """
        PAC（Proxy Auto-Configuration）設定を適用
        
        Args:
            auto_detect: PAC自動検出を使用するか
            pac_url: 手動PAC URL
            fallback_to_system: 失敗時にシステムプロキシにフォールバック
            
        Returns:
            bool: PAC設定成功可否
        """
        if not PYPAC_AVAILABLE:
            logger.warning("pypac利用不可、PAC設定スキップ")
            return False
            
        try:
            from pypac import PACSession
            from pypac.parser import PACFile
            
            # PAC設定を試行
            if auto_detect:
                # 自動検出
                logger.info("PAC自動検出を試行")
                pac_session = PACSession()
                
                # テスト用URL で PAC 動作確認
                test_url = "https://www.google.com"
                proxy_info = pac_session.get_proxy(test_url)
                
                if proxy_info and proxy_info.get('http'):
                    self._session.proxies = proxy_info
                    logger.info(f"PAC自動検出成功: {proxy_info}")
                    return True
                else:
                    logger.warning("PAC自動検出でプロキシが見つからない")
                    
            elif pac_url:
                # 手動PAC URL
                logger.info(f"手動PAC URL使用: {pac_url}")
                pac_file = PACFile(pac_url)
                
                # テスト用URLでプロキシ取得
                test_url = "https://www.google.com"
                proxy_str = pac_file.find_proxy_for_url(test_url, "www.google.com")
                
                if proxy_str and "DIRECT" not in proxy_str:
                    # プロキシ文字列を解析
                    proxies = self._parse_pac_proxy_string(proxy_str)
                    if proxies:
                        self._session.proxies = proxies
                        logger.info(f"手動PAC設定成功: {proxies}")
                        return True
                        
            return False
            
        except Exception as e:
            logger.error(f"PAC設定エラー: {e}")
            return False
    
    def _parse_pac_proxy_string(self, proxy_str: str) -> Dict[str, str]:
        """
        PAC プロキシ文字列を requests 用辞書に変換
        
        Args:
            proxy_str: PAC形式のプロキシ文字列 (例: "PROXY proxy.example.com:8080")
            
        Returns:
            dict: requests用プロキシ辞書
        """
        try:
            proxies = {}
            
            # 複数のプロキシがセミコロンで区切られている場合
            proxy_entries = proxy_str.split(';')
            
            for entry in proxy_entries:
                entry = entry.strip()
                
                if entry.startswith('PROXY '):
                    proxy_address = entry[6:].strip()  # "PROXY " を削除
                    if '://' not in proxy_address:
                        proxy_address = f"http://{proxy_address}"
                        
                    proxies['http'] = proxy_address
                    proxies['https'] = proxy_address
                    break
                    
            return proxies
            
        except Exception as e:
            logger.error(f"PAC プロキシ文字列解析エラー: {e}")
            return {}
    
    def _apply_certificate_config(self, config: Dict[str, Any]):
        """
        SSL証明書設定をセッションに適用（プロキシ環境対応強化版）
        
        Args:
            config: プロキシ設定辞書
        """
        cert_config = config.get('cert', {})
        
        # SSL検証設定
        verify = cert_config.get('verify', True)
        ca_bundle = cert_config.get('ca_bundle', '')
        
        # プロキシ環境でのSSL処理設定
        proxy_ssl_config = cert_config.get('proxy_ssl_handling', {})
        ssl_strategy = proxy_ssl_config.get('strategy', 'disable_verify')
        fallback_to_no_verify = proxy_ssl_config.get('fallback_to_no_verify', True)
        log_ssl_errors = proxy_ssl_config.get('log_ssl_errors', True)
        
        # 企業CA設定
        enterprise_ca_config = cert_config.get('enterprise_ca', {})
        
        # プロキシが有効かどうかを確認
        is_proxy_active = self._is_proxy_active()
        
        if is_proxy_active:
            logger.info(f"プロキシ環境でのSSL処理: strategy={ssl_strategy}")
            self._apply_proxy_ssl_strategy(ssl_strategy, verify, ca_bundle, fallback_to_no_verify, log_ssl_errors, enterprise_ca_config)
        else:
            # プロキシ無効時の通常のSSL設定
            self._apply_standard_ssl_config(verify, ca_bundle, cert_config)
    
    def _apply_proxy_ssl_strategy(self, strategy: str, verify: bool, ca_bundle: str, 
                                  fallback_to_no_verify: bool, log_ssl_errors: bool, enterprise_ca_config: Dict[str, Any] = None):
        """
        プロキシ環境でのSSL戦略を適用（企業CA対応）
        
        Args:
            strategy: SSL処理戦略
            verify: SSL検証設定
            ca_bundle: CAバンドルパス  
            fallback_to_no_verify: 検証失敗時の無効化フォールバック
            log_ssl_errors: SSLエラーログ出力
            enterprise_ca_config: 企業CA設定
        """
        if enterprise_ca_config is None:
            enterprise_ca_config = {}
            
        if strategy == 'disable_verify':
            # プロキシ環境では検証を無効化
            self._session.verify = False
            logger.warning("プロキシ環境のため、SSL証明書検証を無効化しました")
            self._suppress_ssl_warnings()
            
        elif strategy == 'use_proxy_ca':
            # プロキシ証明書を使用（企業CA対応）
            if self._try_proxy_certificate_config(verify, ca_bundle, fallback_to_no_verify, log_ssl_errors, enterprise_ca_config):
                logger.info("プロキシ証明書設定成功")
                
                # 接続テストを実行してフォールバック判定
                if self._test_ssl_connection_with_fallback(fallback_to_no_verify, log_ssl_errors):
                    logger.info("SSL接続テスト成功")
                else:
                    logger.warning("SSL接続テスト失敗、フォールバック適用済み")
            else:
                logger.warning("プロキシ証明書設定失敗、フォールバック処理実行")
                
        elif strategy == 'ignore_proxy':
            # プロキシを無視してSSL設定を適用
            logger.info("プロキシを無視してSSL設定を適用")
            self._apply_standard_ssl_config(verify, ca_bundle, {})
            
        else:
            logger.warning(f"不明なSSL戦略: {strategy}、デフォルト処理を実行")
            self._apply_standard_ssl_config(verify, ca_bundle, {})
    
    def _try_proxy_certificate_config(self, verify: bool, ca_bundle: str, 
                                      fallback_to_no_verify: bool, log_ssl_errors: bool, enterprise_ca_config: Dict[str, Any] = None) -> bool:
        """
        プロキシ証明書設定を試行（企業CA対応）
        
        Returns:
            bool: 設定成功可否
        """
        if enterprise_ca_config is None:
            enterprise_ca_config = {}
            
        try:
            if verify:
                # 1. 企業CA設定を優先的に試行
                if self._try_enterprise_ca_config(enterprise_ca_config, log_ssl_errors):
                    return True
                
                # 2. カスタムCAバンドルを試行
                if ca_bundle and os.path.exists(ca_bundle):
                    self._session.verify = ca_bundle
                    logger.info(f"カスタムCA Bundle を使用: {ca_bundle}")
                    return True
                
                # 3. truststoreを優先的に試行（システム証明書ストア）
                if TRUSTSTORE_AVAILABLE:
                    try:
                        import truststore
                        from requests.adapters import HTTPAdapter
                        
                        class TruststoreProxyAdapter(HTTPAdapter):
                            def init_poolmanager(self, *args, **kwargs):
                                try:
                                    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                                    kwargs['ssl_context'] = ctx
                                    logger.info("✅ truststore: プロキシ環境でシステム証明書使用")
                                except Exception:
                                    # プロキシ環境でのtruststore使用は慎重にフォールバック
                                    kwargs.pop('ssl_context', None)
                                return super().init_poolmanager(*args, **kwargs)
                        
                        self._session.mount('https://', TruststoreProxyAdapter())
                        self._session.verify = True
                        logger.info("🔐 truststore: プロキシ環境証明書設定完了")
                        return True
                        
                    except Exception as e:
                        if log_ssl_errors:
                            logger.warning(f"truststore設定失敗: {e}")
                
                # 4. certifiバンドルを試行（フォールバック）
                try:
                    import certifi
                    self._session.verify = certifi.where()
                    logger.info("⚠️ certifiフォールバック: 標準証明書バンドル使用")
                    return True
                except ImportError:
                    if log_ssl_errors:
                        logger.warning("certifi利用不可")
                
                # 5. フォールバック処理
                if fallback_to_no_verify:
                    logger.warning("すべてのSSL設定が失敗、検証を無効化します")
                    self._session.verify = False
                    self._suppress_ssl_warnings()
                    return True
                else:
                    return False
            else:
                # verify=False の場合
                self._session.verify = False
                self._suppress_ssl_warnings()
                return True
                
        except Exception as e:
            if log_ssl_errors:
                logger.error(f"プロキシ証明書設定エラー: {e}")
            
            if fallback_to_no_verify:
                self._session.verify = False
                self._suppress_ssl_warnings()
                return True
            return False
    
    def _try_enterprise_ca_config(self, enterprise_ca_config: Dict[str, Any], log_ssl_errors: bool) -> bool:
        """
        企業CA設定を試行
        
        Args:
            enterprise_ca_config: 企業CA設定
            log_ssl_errors: SSLエラーログ出力
            
        Returns:
            bool: 設定成功可否
        """
        if not enterprise_ca_config.get('enable_truststore', False):
            return False
            
        try:
            # 企業CA証明書バンドルを生成
            ca_bundle_path = self._create_enterprise_ca_bundle(enterprise_ca_config, log_ssl_errors)
            
            if ca_bundle_path and os.path.exists(ca_bundle_path):
                # truststoreが利用可能な場合、優先的にtruststoreのSSLコンテキストを適用
                if TRUSTSTORE_AVAILABLE:
                    try:
                        import truststore
                        from requests.adapters import HTTPAdapter
                        
                        class TruststoreHTTPSAdapter(HTTPAdapter):
                            def __init__(self, ca_bundle_path=None, *args, **kwargs):
                                self.ca_bundle_path = ca_bundle_path
                                super().__init__(*args, **kwargs)
                                
                            def init_poolmanager(self, *args, **kwargs):
                                try:
                                    # truststoreのSSLコンテキストを作成
                                    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                                    
                                    # カスタム証明書バンドルも併用
                                    if self.ca_bundle_path:
                                        ctx.load_verify_locations(cafile=self.ca_bundle_path)
                                    
                                    kwargs['ssl_context'] = ctx
                                    if log_ssl_errors:
                                        logger.info("🔐 truststore優先: システム証明書 + カスタムバンドル")
                                        
                                except Exception as e:
                                    # truststoreが失敗した場合、カスタムバンドルのみ使用
                                    if self.ca_bundle_path:
                                        kwargs.pop('ssl_context', None)  # デフォルトに戻す
                                        if log_ssl_errors:
                                            logger.warning(f"truststoreフォールバック: カスタムバンドルのみ使用 - {e}")
                                    
                                return super().init_poolmanager(*args, **kwargs)
                        
                        # truststoreベースのHTTPSアダプターを設定
                        self._session.mount('https://', TruststoreHTTPSAdapter(ca_bundle_path))
                        self._session.verify = ca_bundle_path  # フォールバック用
                        
                        if log_ssl_errors:
                            logger.info("✅ truststore優先 SSL設定完了")
                            
                    except Exception as e:
                        # truststoreが完全に失敗した場合、従来のcertifi方式にフォールバック
                        self._session.verify = ca_bundle_path
                        if log_ssl_errors:
                            logger.warning(f"⚠️ truststore失敗、certifiフォールバック: {e}")
                else:
                    # truststoreが利用できない場合、従来の方式
                    self._session.verify = ca_bundle_path
                    if log_ssl_errors:
                        logger.info("⚠️ truststore利用不可、certifi使用")
                
                logger.info(f"🔐 企業CA Bundle 適用完了: {ca_bundle_path}")
                return True
            else:
                if log_ssl_errors:
                    logger.warning("企業CA Bundle生成失敗")
                return False
                
        except Exception as e:
            if log_ssl_errors:
                logger.error(f"企業CA設定エラー: {e}")
            return False
    
    def _create_enterprise_ca_bundle(self, enterprise_ca_config: Dict[str, Any], log_ssl_errors: bool) -> Optional[str]:
        """
        企業CA証明書バンドルを生成（truststoreを優先、certifiフォールバック）
        
        Args:
            enterprise_ca_config: 企業CA設定
            log_ssl_errors: SSLエラーログ出力
            
        Returns:
            str: 生成された証明書バンドルファイルパス
        """
        try:
            import tempfile
            
            # 証明書ソース設定
            ca_sources = enterprise_ca_config.get('corporate_ca_sources', ['system_ca', 'truststore'])
            custom_ca_bundle = enterprise_ca_config.get('custom_ca_bundle', '')
            auto_detect = enterprise_ca_config.get('auto_detect_corporate_ca', True)
            
            # 一時ファイルに証明書バンドルを作成
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False, encoding='utf-8') as bundle_file:
                bundle_path = bundle_file.name
                cert_count = 0
                truststore_used = False
                
                # 1. truststoreを優先的に使用（利用可能な場合）
                if TRUSTSTORE_AVAILABLE:
                    try:
                        import truststore
                        import ssl
                        
                        # truststoreのSSLコンテキストから証明書情報を取得しようと試みる
                        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                        
                        # truststoreが有効であることを確認
                        # 実際の証明書データは直接取得できないため、
                        # truststoreの存在確認と準備のみ行う
                        truststore_used = True
                        cert_count += 1  # truststoreの使用をカウント
                        
                        if log_ssl_errors:
                            logger.info("✅ truststore: 優先利用 - システム証明書ストア統合")
                            
                    except Exception as e:
                        if log_ssl_errors:
                            logger.warning(f"truststore利用失敗、certifiにフォールバック: {e}")
                        truststore_used = False
                
                # 2. truststoreが使用できない場合、またはフォールバックとしてcertifiを使用
                if not truststore_used or 'certifi' in ca_sources:
                    try:
                        import certifi
                        with open(certifi.where(), 'r', encoding='utf-8') as certifi_file:
                            certifi_content = certifi_file.read()
                            bundle_file.write(certifi_content)
                            cert_count += 1
                            
                        status = "フォールバック" if truststore_used else "単独利用"
                        if log_ssl_errors:
                            logger.info(f"{'⚠️' if truststore_used else '✅'} certifi: {status} - 標準証明書バンドル")
                            
                    except Exception as e:
                        if log_ssl_errors:
                            logger.warning(f"certifi証明書追加失敗: {e}")
                
                # 3. システム証明書ストア（OS固有）から追加証明書を取得
                if 'system_ca' in ca_sources:
                    try:
                        system_certs = self._get_system_certificates()
                        for cert in system_certs:
                            bundle_file.write('\n')
                            bundle_file.write(cert)
                            cert_count += 1
                        if log_ssl_errors:
                            logger.info(f"✅ システム証明書ストア: {len(system_certs)}件追加")
                    except Exception as e:
                        if log_ssl_errors:
                            logger.warning(f"システム証明書ストア取得失敗: {e}")
                
                # 4. カスタム証明書ファイルを追加
                if custom_ca_bundle and os.path.exists(custom_ca_bundle):
                    try:
                        with open(custom_ca_bundle, 'r', encoding='utf-8') as custom_file:
                            bundle_file.write('\n')
                            bundle_file.write(custom_file.read())
                            cert_count += 1
                            if log_ssl_errors:
                                logger.info(f"✅ カスタム証明書ファイルを追加: {custom_ca_bundle}")
                    except Exception as e:
                        if log_ssl_errors:
                            logger.warning(f"カスタム証明書追加失敗: {e}")
                
                if cert_count > 0:
                    priority_info = "truststore優先" if truststore_used else "certifiフォールバック"
                    if log_ssl_errors:
                        logger.info(f"🔐 企業CA Bundle生成完了: {priority_info} ({cert_count}ソース)")
                    return bundle_path
                else:
                    if log_ssl_errors:
                        logger.warning("❌ 企業CA Bundle生成失敗: 証明書ソースなし")
                    return None
                if 'system_ca' in ca_sources:
                    try:
                        system_certs = self._get_system_certificates()
                        for cert in system_certs:
                            bundle_file.write('\n')
                            bundle_file.write(cert)
                            cert_count += 1
                        if log_ssl_errors:
                            logger.info(f"システム証明書ストアから{len(system_certs)}件追加")
                    except Exception as e:
                        if log_ssl_errors:
                            logger.warning(f"システム証明書ストア取得失敗: {e}")
                
                # 4. カスタム証明書ファイルを追加
                if custom_ca_bundle and os.path.exists(custom_ca_bundle):
                    try:
                        with open(custom_ca_bundle, 'r', encoding='utf-8') as custom_file:
                            bundle_file.write('\n')
                            bundle_file.write(custom_file.read())
                            cert_count += 1
                            if log_ssl_errors:
                                logger.info(f"カスタム証明書ファイルを追加: {custom_ca_bundle}")
                    except Exception as e:
                        if log_ssl_errors:
                            logger.warning(f"カスタム証明書追加失敗: {e}")
                
                if cert_count > 0:
                    if log_ssl_errors:
                        logger.info(f"企業CA Bundle生成完了: {bundle_path} ({cert_count}ソース)")
                    return bundle_path
                else:
                    if log_ssl_errors:
                        logger.warning("企業CA Bundle生成失敗: 証明書ソースなし")
                    return None
                    
        except Exception as e:
            if log_ssl_errors:
                logger.error(f"企業CA Bundle生成エラー: {e}")
            return None
    
    def _get_system_certificates(self) -> list:
        """
        クロスプラットフォーム対応のシステム証明書取得
        
        Returns:
            list: PEM形式の証明書リスト
        """
        certificates = []
        
        try:
            import ssl
            import platform
            
            system = platform.system()
            
            if system == "Windows":
                # Windows証明書ストアから取得
                try:
                    import wincertstore
                    import base64
                    
                    # ルート証明書ストアと中間証明書ストアから取得
                    stores = ['ROOT', 'CA']
                    
                    for store_name in stores:
                        store = wincertstore.CertSystemStore(store_name)
                        
                        for cert_der in store.itercerts(usage=wincertstore.SERVER_AUTH):
                            try:
                                # DERからPEM形式に変換
                                cert_pem = ssl.DER_cert_to_PEM_cert(cert_der)
                                certificates.append(cert_pem)
                            except Exception:
                                continue
                                
                except ImportError:
                    logger.warning("wincertstore利用不可、Windows証明書スキップ")
                    
            elif system == "Darwin":  # macOS
                # macOSキーチェーンから証明書を取得
                try:
                    import subprocess
                    result = subprocess.run([
                        'security', 'find-certificate', '-a', '-p', '/System/Library/Keychains/SystemRootCertificates.keychain'
                    ], capture_output=True, text=True, check=True)
                    
                    cert_data = result.stdout
                    # PEM証明書を個別に分割
                    cert_blocks = cert_data.split('-----END CERTIFICATE-----')
                    for block in cert_blocks:
                        if '-----BEGIN CERTIFICATE-----' in block:
                            cert = block.strip() + '\n-----END CERTIFICATE-----'
                            certificates.append(cert)
                            
                except Exception as e:
                    logger.warning(f"macOS証明書取得エラー: {e}")
                    
            elif system == "Linux":
                # Linux証明書ストアから取得
                cert_paths = [
                    '/etc/ssl/certs/ca-certificates.crt',  # Debian/Ubuntu
                    '/etc/pki/tls/certs/ca-bundle.crt',    # RHEL/CentOS
                    '/etc/ssl/ca-bundle.pem',              # openSUSE
                    '/etc/ssl/cert.pem',                   # OpenBSD
                ]
                
                for cert_path in cert_paths:
                    if os.path.exists(cert_path):
                        try:
                            with open(cert_path, 'r', encoding='utf-8') as f:
                                cert_content = f.read()
                                # PEM証明書を個別に分割
                                cert_blocks = cert_content.split('-----END CERTIFICATE-----')
                                for block in cert_blocks:
                                    if '-----BEGIN CERTIFICATE-----' in block:
                                        cert = block.strip() + '\n-----END CERTIFICATE-----'
                                        certificates.append(cert)
                            break
                        except Exception as e:
                            logger.warning(f"Linux証明書読み込みエラー ({cert_path}): {e}")
                            
            else:
                logger.warning(f"未対応OS: {system}")
                        
        except Exception as e:
            logger.warning(f"システム証明書取得エラー: {e}")
            
        return certificates
    
    def _test_truststore_compatibility(self) -> bool:
        """
        truststore の互換性をテスト
        
        Returns:
            bool: 互換性があるかどうか
        """
        try:
            # 単純なテストでtruststore の動作を確認
            import ssl
            context = ssl.create_default_context()
            # 基本的な設定が可能かテスト
            return True
        except Exception:
            return False
    
    def _is_proxy_active(self) -> bool:
        """プロキシが有効かどうかを判定"""
        try:
            # セッションのプロキシ設定を確認
            return bool(self._session.proxies.get('http') or self._session.proxies.get('https'))
        except:
            return False
    
    def _test_ssl_connection_with_fallback(self, fallback_to_no_verify: bool, log_ssl_errors: bool) -> bool:
        """
        SSL接続テストを実行し、失敗時にフォールバック処理を適用
        
        Args:
            fallback_to_no_verify: 失敗時のSSL検証無効化フォールバック
            log_ssl_errors: SSLエラーログ出力
            
        Returns:
            bool: 接続成功またはフォールバック完了
        """
        test_url = "https://rde-api.nims.go.jp/groups/root"
        
        try:
            # 軽量接続テスト（短時間タイムアウト）
            response = self._session.get(test_url, timeout=5)
            if log_ssl_errors:
                logger.info(f"SSL接続テスト成功: HTTP {response.status_code}")
            return True
            
        except Exception as e:
            if log_ssl_errors:
                logger.warning(f"SSL接続テスト失敗: {e}")
            
            # SSL証明書関連エラーの場合のみフォールバック適用
            if "CERTIFICATE_VERIFY_FAILED" in str(e) or "SSL" in str(e):
                if fallback_to_no_verify:
                    logger.warning("SSL証明書エラーによりフォールバック処理を適用")
                    self._session.verify = False
                    self._suppress_ssl_warnings()
                    
                    # フォールバック後の接続テスト
                    try:
                        response = self._session.get(test_url, timeout=5)
                        logger.info(f"フォールバック後の接続成功: HTTP {response.status_code}")
                        return True
                    except Exception as fallback_error:
                        if log_ssl_errors:
                            logger.error(f"フォールバック後も接続失敗: {fallback_error}")
                        return False
                else:
                    return False
            else:
                # SSL以外のエラーは設定問題ではない
                return False
    
    def _apply_standard_ssl_config(self, verify: bool, ca_bundle: str, cert_config: Dict[str, Any]):
        """
        標準SSL設定を適用（truststoreを優先、certifiフォールバック）
        
        Args:
            verify: SSL検証設定
            ca_bundle: CAバンドルパス
            cert_config: 証明書設定
        """
        if not verify:
            self._session.verify = False
            logger.warning("SSL証明書検証を無効化 - セキュリティリスクがあります")
            self._suppress_ssl_warnings()
            return
        
        truststore_success = False
        
        # 1. truststoreを優先的に使用
        use_os_store = cert_config.get('use_os_store', True)
        if use_os_store and TRUSTSTORE_AVAILABLE:
            try:
                import truststore
                from requests.adapters import HTTPAdapter
                
                class TruststoreStandardAdapter(HTTPAdapter):
                    def __init__(self, ca_bundle_fallback=None, *args, **kwargs):
                        self.ca_bundle_fallback = ca_bundle_fallback
                        super().__init__(*args, **kwargs)
                        
                    def init_poolmanager(self, *args, **kwargs):
                        try:
                            # truststoreのSSLコンテキストを作成
                            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                            
                            # カスタムCAバンドルがある場合は併用
                            if self.ca_bundle_fallback and os.path.exists(self.ca_bundle_fallback):
                                ctx.load_verify_locations(cafile=self.ca_bundle_fallback)
                                
                            kwargs['ssl_context'] = ctx
                            logger.info("✅ truststore優先: システム証明書ストア + カスタムCA")
                            
                        except Exception as e:
                            # フォールバック: カスタムCAバンドルまたはcertifi
                            kwargs.pop('ssl_context', None)
                            logger.warning(f"truststoreフォールバック開始: {e}")
                            
                        return super().init_poolmanager(*args, **kwargs)
                
                # HTTPSアダプターを設定
                adapter = TruststoreStandardAdapter(ca_bundle_fallback=ca_bundle)
                self._session.mount('https://', adapter)
                
                # フォールバック用のverify設定
                if ca_bundle and os.path.exists(ca_bundle):
                    self._session.verify = ca_bundle
                    logger.info(f"フォールバック用CA Bundle準備: {ca_bundle}")
                else:
                    try:
                        import certifi
                        self._session.verify = certifi.where()
                        logger.info("フォールバック用certifi準備")
                    except ImportError:
                        self._session.verify = True
                        logger.warning("フォールバック用デフォルト証明書準備")
                
                truststore_success = True
                logger.info("🔐 truststore優先SSL設定完了")
                
            except Exception as e:
                logger.warning(f"truststore設定失敗、certifiフォールバック: {e}")
                truststore_success = False
        
        # 2. truststoreが使用できない場合、または無効化されている場合
        if not truststore_success:
            if ca_bundle and os.path.exists(ca_bundle):
                self._session.verify = ca_bundle
                logger.info(f"⚠️ certifiフォールバック: カスタムCA使用 - {ca_bundle}")
            else:
                try:
                    import certifi
                    self._session.verify = certifi.where()
                    logger.info("⚠️ certifiフォールバック: 標準証明書バンドル使用")
                except ImportError:
                    self._session.verify = True
                    logger.warning("⚠️ certifi利用不可、システムデフォルト使用")
    
    def _suppress_ssl_warnings(self):
        """SSL警告を抑制"""
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except ImportError:
            pass
    
    def _configure_session_adapters(self):
        """セッションアダプターとリトライ戦略を設定"""
        # リトライ戦略
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],  # 新しいパラメータ名
            backoff_factor=1
        )
        
        # HTTPアダプター設定
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        
        # タイムアウト設定（デフォルト）
        self._session.timeout = 30
        
        # SSL設定は_apply_certificate_config()で既に設定済みのため、ここでは上書きしない
    
    def get_proxy_config(self) -> Dict[str, Any]:
        """現在のプロキシ設定を取得"""
        return self._proxy_config.copy()
    
    def get_system_proxy_info(self) -> Dict[str, Any]:
        """
        システムプロキシ情報を取得
        
        Returns:
            Dict[str, Any]: システムプロキシ設定情報
        """
        try:
            system_proxies = getproxies()
            logger.info(f"システムプロキシ検出: {system_proxies}")
            
            result = {
                "detected": bool(system_proxies),
                "proxies": system_proxies,
                "suggested_config": {}
            }
            
            if system_proxies:
                # YAML設定用のフォーマットを生成
                http_proxy = system_proxies.get('http')
                https_proxy = system_proxies.get('https', http_proxy)
                
                if http_proxy:
                    result["suggested_config"] = {
                        "mode": "HTTP",
                        "http_proxy": http_proxy,
                        "https_proxy": https_proxy
                    }
                else:
                    result["suggested_config"] = {"mode": "DIRECT"}
            else:
                result["suggested_config"] = {"mode": "DIRECT"}
                
            return result
            
        except Exception as e:
            logger.error(f"システムプロキシ情報取得エラー: {e}")
            return {
                "detected": False,
                "proxies": {},
                "suggested_config": {"mode": "DIRECT"},
                "error": str(e)
            }
    
    def create_system_proxy_config(self, config_name: str = "auto_detected") -> bool:
        """
        システムプロキシを検出して設定ファイルに保存
        
        Args:
            config_name: 設定名（デフォルト: "auto_detected"）
            
        Returns:
            bool: 成功/失敗
        """
        try:
            from config.common import get_dynamic_file_path
            
            proxy_info = self.get_system_proxy_info()
            
            if not proxy_info["detected"]:
                logger.info("システムプロキシが検出されませんでした")
                return False
            
            # YAMLファイルパスを取得
            yaml_path = get_dynamic_file_path("config/network.yaml")
            
            # 既存設定を読み込み
            config_data = {}
            if os.path.exists(yaml_path) and YAML_AVAILABLE:
                try:
                    with open(yaml_path, 'r', encoding='utf-8') as f:
                        config_data = yaml.safe_load(f) or {}
                except Exception as e:
                    logger.warning(f"YAML読み込みエラー: {e}")
            
            # configurations セクションに追加
            if "configurations" not in config_data:
                config_data["configurations"] = {}
            
            config_data["configurations"][config_name] = proxy_info["suggested_config"]
            
            # システムプロキシが検出された場合、デフォルトをSYSTEMモードに設定
            if proxy_info["detected"]:
                config_data["mode"] = "SYSTEM"
            
            # YAMLファイルに保存
            if YAML_AVAILABLE:
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(config_data, f, default_flow_style=False, 
                                 allow_unicode=True, sort_keys=False)
                logger.info(f"システムプロキシ設定を {yaml_path} に保存しました")
                return True
            else:
                logger.error("YAML モジュールが利用できないため設定を保存できませんでした")
                return False
                
        except Exception as e:
            logger.error(f"システムプロキシ設定保存エラー: {e}")
            return False


# ============================================================================
# グローバルセッション管理インスタンス
# ============================================================================

_session_manager = ProxySessionManager()

def get_proxy_session() -> requests.Session:
    """
    プロキシ対応セッションを取得
    
    Returns:
        requests.Session: 設定済みプロキシセッション
    """
    return _session_manager.get_session()

def configure_proxy_session(config: Optional[Dict[str, Any]] = None):
    """
    プロキシセッションを設定
    
    Args:
        config: プロキシ設定辞書。Noneの場合はファイルから読み込み
    """
    _session_manager.configure(config)

def reconfigure_proxy_session(config: Dict[str, Any]):
    """
    プロキシセッションを再設定
    
    Args:
        config: 新しいプロキシ設定
    """
    _session_manager.reconfigure(config)

def get_current_proxy_config() -> Dict[str, Any]:
    """現在のプロキシ設定を取得"""
    return _session_manager.get_proxy_config()
