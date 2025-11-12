"""
TokenManager - RefreshToken対応トークン管理

OAuth2 RefreshTokenを使用した自動/手動トークンリフレッシュ機能を提供。
AccessTokenの有効期限を監視し、期限切れ前に自動更新を実行。

主な機能:
- RefreshToken/AccessTokenの保存・読み込み
- JWT expiry解析による有効期限管理
- QTimer-based自動リフレッシュ (60秒間隔チェック、5分前マージン)
- 手動リフレッシュAPI
- エラーハンドリング (RefreshToken期限切れ→再ログイン誘導)

設計仕様: docs/development/TOKEN_MANAGER_DESIGN_SPEC.md
検証実装: tools/test_token_refresh.py
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import base64

from PySide6.QtCore import QObject, QTimer, Signal

from config import common
from net.http_helpers import proxy_post


logger = logging.getLogger(__name__)


# ========================================
# Data Structures
# ========================================

@dataclass
class TokenData:
    """
    トークンデータ構造
    
    Attributes:
        access_token: OAuth2 AccessToken (JWT)
        refresh_token: OAuth2 RefreshToken (JWT)
        expires_at: AccessToken有効期限 (ISO 8601 UTC)
        updated_at: 最終更新日時 (ISO 8601 UTC)
        token_type: トークンタイプ (通常 "Bearer")
    """
    access_token: str
    refresh_token: str
    expires_at: str  # ISO 8601 format (UTC)
    updated_at: str  # ISO 8601 format (UTC)
    token_type: str = "Bearer"
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換 (JSON保存用)"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TokenData':
        """辞書から復元"""
        return cls(**data)
    
    def is_expired(self, margin_seconds: int = 300) -> bool:
        """
        トークンの有効期限チェック
        
        Args:
            margin_seconds: 有効期限前のマージン秒数 (デフォルト300秒=5分)
        
        Returns:
            True: 期限切れまたはマージン時間内
            False: まだ有効
        """
        try:
            expires = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            margin = timedelta(seconds=margin_seconds)
            
            return (expires - now) <= margin
        except Exception as e:
            logger.error(f"有効期限チェックエラー: {e}")
            return True  # エラー時は期限切れとして扱う


# ========================================
# OAuth2 Token Refresh
# ========================================

class OAuth2TokenRefresh:
    """
    OAuth2 Token Refresh実装
    
    Azure AD B2C Token Endpointへのリフレッシュリクエストを実行。
    net.http_helpers経由で実装 (アプリルール準拠)
    
    複数ホスト対応: ホスト名に応じて適切なCLIENT_ID/SCOPEを使用
    
    参考実装: tools/test_token_refresh.py (検証済み)
    """
    
    # Azure AD B2C設定
    TOKEN_ENDPOINT = "https://dicelogin.b2clogin.com/dicelogin.onmicrosoft.com/b2c_1a_dpf_signin/oauth2/v2.0/token"
    
    # ホスト→CLIENT_ID/SCOPEマッピング
    HOST_CONFIG = {
        "rde.nims.go.jp": {
            "client_id": "6ff53d1d-7aee-445e-a01a-2b4c82ea84e1",
            "scope": "openid profile offline_access 6ff53d1d-7aee-445e-a01a-2b4c82ea84e1"
        },
        "rde-material.nims.go.jp": {
            "client_id": "329b7bb7-02c9-4437-a5cf-9742d238d3bf",
            "scope": "openid profile offline_access 329b7bb7-02c9-4437-a5cf-9742d238d3bf"
        }
    }
    
    # デフォルト設定（後方互換性）
    CLIENT_ID = "6ff53d1d-7aee-445e-a01a-2b4c82ea84e1"
    SCOPE = "openid profile offline_access 6ff53d1d-7aee-445e-a01a-2b4c82ea84e1"
    
    @classmethod
    def refresh_token(cls, refresh_token: str, host: Optional[str] = None, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        RefreshTokenを使用して新しいトークンを取得
        
        Args:
            refresh_token: 現在のRefreshToken
            host: ホスト名 (省略時はデフォルトCLIENT_ID使用)
            timeout: タイムアウト秒数
        
        Returns:
            成功時: {
                'access_token': str,
                'refresh_token': str,
                'expires_in': int,
                'token_type': str
            }
            失敗時: None
        
        Raises:
            なし (エラーはログ出力してNone返却)
        """
        try:
            # ホスト設定取得
            if host and host in cls.HOST_CONFIG:
                config = cls.HOST_CONFIG[host]
                client_id = config["client_id"]
                scope = config["scope"]
                logger.info(f"Token Refresh開始 (host: {host}, client_id: {client_id[:8]}...)")
            else:
                client_id = cls.CLIENT_ID
                scope = cls.SCOPE
                logger.info(f"Token Refresh開始 (デフォルト設定)")
            
            # OAuth2 Refresh Token Request
            # grant_type=refresh_tokenでPOST
            # scope省略でRefreshTokenの元のscopeを継承
            # 参考: tools/test_token_refresh.py (検証済み実装)
            request_data = {
                'grant_type': 'refresh_token',
                'client_id': client_id,
                'refresh_token': refresh_token
            }
            
            # scopeパラメータは省略（RefreshTokenの元のscopeを継承）
            # Azure AD B2Cは複数リソースscopeをサポートしないため、
            # RefreshToken時はscopeを指定せず、元の権限を継承させる
            
            response = proxy_post(
                cls.TOKEN_ENDPOINT,
                data=request_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                timeout=timeout
            )
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info(f"Token Refresh成功 (expires_in: {token_data.get('expires_in')}秒)")
                return token_data
            else:
                logger.error(f"Token Refresh失敗: HTTP {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Token Refresh例外: {e}", exc_info=True)
            return None


# ========================================
# Token Manager (Singleton)
# ========================================

class TokenManager(QObject):
    """
    トークン管理マネージャー (シングルトン)
    
    RefreshToken/AccessTokenのライフサイクル管理を一元化。
    自動リフレッシュタイマーによる期限切れ前の自動更新を実行。
    
    使用方法:
        manager = TokenManager.get_instance()
        manager.start_auto_refresh()
        
        # ログイン後
        manager.save_tokens(
            host='rde.nims.go.jp',
            access_token='...',
            refresh_token='...',
            expires_in=3600
        )
        
        # トークン取得
        token = manager.get_access_token('rde.nims.go.jp')
        
        # 手動リフレッシュ
        success = manager.refresh_access_token('rde.nims.go.jp')
    """
    
    # シングルトンインスタンス
    _instance: Optional['TokenManager'] = None
    
    # v2.0.3: 管理対象ホスト（この2つのみ使用）
    ACTIVE_HOSTS = ['rde.nims.go.jp', 'rde-material.nims.go.jp']
    
    # Qt Signals (PySide6)
    token_refreshed = Signal(str)  # host: トークン更新成功
    token_refresh_failed = Signal(str, str)  # host, error: トークン更新失敗
    token_expired = Signal(str)  # host: RefreshToken期限切れ (再ログイン必要)
    
    def __init__(self):
        """
        コンストラクタ (外部から直接呼び出し禁止)
        get_instance()を使用すること
        """
        if TokenManager._instance is not None:
            raise RuntimeError("TokenManager is singleton. Use get_instance()")
        
        super().__init__()
        
        # 自動リフレッシュタイマー
        self._auto_refresh_timer: Optional[QTimer] = None
        self._auto_refresh_interval = 60 * 1000  # 60秒 (ミリ秒)
        
        # 設定
        self._refresh_margin_seconds = 300  # 5分前にリフレッシュ
        self._retry_max_attempts = 3
        self._retry_backoff_seconds = 30
        
        logger.info("TokenManager初期化完了")
    
    @classmethod
    def get_instance(cls) -> 'TokenManager':
        """シングルトンインスタンス取得"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    # ========================================
    # Token File I/O
    # ========================================
    
    def save_tokens(
        self,
        host: str,
        access_token: str,
        refresh_token: str,
        expires_in: int
    ) -> bool:
        """
        トークンを保存
        
        Args:
            host: ホスト名 (例: 'rde.nims.go.jp')
            access_token: OAuth2 AccessToken
            refresh_token: OAuth2 RefreshToken
            expires_in: AccessToken有効期限 (秒)
        
        Returns:
            True: 保存成功
            False: 保存失敗
        """
        try:
            # 有効期限計算
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=expires_in)
            
            # TokenData作成
            token_data = TokenData(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at.isoformat(),
                updated_at=now.isoformat(),
                token_type="Bearer"
            )
            
            # ファイル読み込み (既存データ取得)
            tokens_file = Path(common.BEARER_TOKENS_FILE)
            tokens_dict = {}
            
            if tokens_file.exists():
                try:
                    with open(tokens_file, 'r', encoding='utf-8') as f:
                        tokens_dict = json.load(f)
                except Exception as e:
                    logger.warning(f"既存トークンファイル読み込みエラー: {e}")
            
            # 更新
            tokens_dict[host] = token_data.to_dict()
            
            # ファイル書き込み
            tokens_file.parent.mkdir(parents=True, exist_ok=True)
            with open(tokens_file, 'w', encoding='utf-8') as f:
                json.dump(tokens_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"トークン保存成功: {host} (expires_at: {expires_at.isoformat()})")
            return True
            
        except Exception as e:
            logger.error(f"トークン保存エラー: {e}", exc_info=True)
            return False
    
    def load_tokens(self, host: str) -> Optional[TokenData]:
        """
        トークン読み込み
        
        Args:
            host: ホスト名
        
        Returns:
            TokenData: トークンデータ
            None: トークンが存在しない、または読み込みエラー
        """
        try:
            tokens_file = Path(common.BEARER_TOKENS_FILE)
            
            if not tokens_file.exists():
                logger.debug(f"トークンファイルが存在しません: {tokens_file}")
                return None
            
            with open(tokens_file, 'r', encoding='utf-8') as f:
                tokens_dict = json.load(f)
            
            if host not in tokens_dict:
                logger.debug(f"ホスト '{host}' のトークンが存在しません")
                return None
            
            token_data = TokenData.from_dict(tokens_dict[host])
            return token_data
            
        except Exception as e:
            logger.error(f"トークン読み込みエラー: {e}", exc_info=True)
            return None
    
    def _load_all_tokens(self) -> Dict[str, Dict[str, Any]]:
        """
        全トークン読み込み（内部用）
        
        Returns:
            Dict[host, token_dict]: 全ホストのトークン辞書
            空辞書: ファイルが存在しない、またはエラー
        """
        try:
            tokens_file = Path(common.BEARER_TOKENS_FILE)
            
            if not tokens_file.exists():
                logger.debug(f"トークンファイルが存在しません: {tokens_file}")
                return {}
            
            with open(tokens_file, 'r', encoding='utf-8') as f:
                tokens_dict = json.load(f)
            
            return tokens_dict
            
        except Exception as e:
            logger.error(f"全トークン読み込みエラー: {e}", exc_info=True)
            return {}
    
    def get_access_token(self, host: str) -> Optional[str]:
        """
        AccessToken取得
        
        Args:
            host: ホスト名
        
        Returns:
            str: AccessToken
            None: トークンが存在しない、または読み込みエラー
        """
        token_data = self.load_tokens(host)
        if token_data:
            return token_data.access_token
        return None
    
    # ========================================
    # Manual Refresh
    # ========================================
    
    def refresh_access_token(self, host: str) -> bool:
        """
        手動トークンリフレッシュ
        
        Args:
            host: ホスト名
        
        Returns:
            True: リフレッシュ成功
            False: リフレッシュ失敗
        """
        try:
            logger.info(f"手動トークンリフレッシュ開始: {host}")
            
            # 既存トークン取得
            token_data = self.load_tokens(host)
            if not token_data:
                logger.error(f"トークンが存在しません: {host}")
                self.token_refresh_failed.emit(host, "トークンが存在しません")
                return False
            
            # Token Refresh実行
            result = OAuth2TokenRefresh.refresh_token(token_data.refresh_token, host=host)
            if not result:
                logger.error(f"Token Refresh失敗: {host}")
                self.token_refresh_failed.emit(host, "Token Refresh APIエラー")
                return False
            
            # 新しいトークン保存
            success = self.save_tokens(
                host=host,
                access_token=result['access_token'],
                refresh_token=result['refresh_token'],
                expires_in=result['expires_in']
            )
            
            if success:
                logger.info(f"トークンリフレッシュ成功: {host}")
                self.token_refreshed.emit(host)
                return True
            else:
                logger.error(f"トークン保存失敗: {host}")
                self.token_refresh_failed.emit(host, "トークン保存エラー")
                return False
                
        except Exception as e:
            logger.error(f"トークンリフレッシュ例外: {e}", exc_info=True)
            self.token_refresh_failed.emit(host, str(e))
            return False
    
    # ========================================
    # Auto Refresh (Timer-based)
    # ========================================
    
    def start_auto_refresh(self):
        """自動リフレッシュタイマー開始"""
        if self._auto_refresh_timer is None:
            self._auto_refresh_timer = QTimer(self)
            self._auto_refresh_timer.timeout.connect(self._auto_refresh_check)
            self._auto_refresh_timer.start(self._auto_refresh_interval)
            logger.info(f"自動リフレッシュタイマー開始 (間隔: {self._auto_refresh_interval}ms)")
    
    def stop_auto_refresh(self):
        """自動リフレッシュタイマー停止"""
        if self._auto_refresh_timer:
            self._auto_refresh_timer.stop()
            logger.info("自動リフレッシュタイマー停止")
    
    def _auto_refresh_check(self):
        """
        自動リフレッシュチェック (タイマーコールバック)
        
        全ホストのトークンをチェックし、期限切れ前のトークンをリフレッシュ
        v2.0.3: アクティブホストのみ処理（クラス定数ACTIVE_HOSTSを使用）
        """
        try:
            tokens_file = Path(common.BEARER_TOKENS_FILE)
            if not tokens_file.exists():
                return
            
            with open(tokens_file, 'r', encoding='utf-8') as f:
                tokens_dict = json.load(f)
            
            for host, token_dict in tokens_dict.items():
                # v2.0.3: クラス定数を使用してアクティブホストのみ処理
                if host not in self.ACTIVE_HOSTS:
                    logger.debug(f"[自動リフレッシュ] 非アクティブホストをスキップ: {host}")
                    continue
                
                try:
                    token_data = TokenData.from_dict(token_dict)
                    
                    # 有効期限チェック (5分前マージン)
                    if token_data.is_expired(self._refresh_margin_seconds):
                        logger.info(f"トークン期限切れ前検出: {host} (自動リフレッシュ実行)")
                        
                        # リフレッシュ実行 (リトライあり)
                        self._refresh_with_retry(host, token_data)
                
                except Exception as e:
                    logger.error(f"トークンチェックエラー ({host}): {e}")
        
        except Exception as e:
            logger.error(f"自動リフレッシュチェック例外: {e}", exc_info=True)
    
    def _refresh_with_retry(self, host: str, token_data: TokenData):
        """
        リトライ付きリフレッシュ
        
        Args:
            host: ホスト名
            token_data: 現在のトークンデータ
        """
        for attempt in range(1, self._retry_max_attempts + 1):
            try:
                logger.info(f"Token Refresh試行 {attempt}/{self._retry_max_attempts}: {host}")
                
                result = OAuth2TokenRefresh.refresh_token(token_data.refresh_token, host=host)
                
                if result:
                    # 成功 → 保存
                    success = self.save_tokens(
                        host=host,
                        access_token=result['access_token'],
                        refresh_token=result['refresh_token'],
                        expires_in=result['expires_in']
                    )
                    
                    if success:
                        logger.info(f"自動リフレッシュ成功: {host}")
                        self.token_refreshed.emit(host)
                        return
                else:
                    # 失敗 → リトライ
                    if attempt < self._retry_max_attempts:
                        logger.warning(f"Token Refresh失敗 (リトライ {attempt}/{self._retry_max_attempts})")
                        import time
                        time.sleep(self._retry_backoff_seconds)
                    else:
                        logger.error(f"Token Refresh最終失敗: {host}")
                        self.token_expired.emit(host)
            
            except Exception as e:
                logger.error(f"Token Refreshリトライ例外 ({attempt}/{self._retry_max_attempts}): {e}")
                if attempt == self._retry_max_attempts:
                    self.token_expired.emit(host)
