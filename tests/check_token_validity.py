"""
トークン有効性チェックツール
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import json
import base64
from datetime import datetime, timezone

def decode_jwt_payload(token: str) -> dict:
    """JWTトークンのペイロードをデコード"""
    try:
        # JWT形式: header.payload.signature
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        
        # Base64デコード（パディング調整）
        payload_b64 = parts[1]
        # パディング追加
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding
        
        payload_json = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_json)
    except Exception as e:
        print(f"デコードエラー: {e}")
        return {}

def check_token_expiry(token: str, host: str):
    """トークンの有効期限をチェック"""
    payload = decode_jwt_payload(token)
    
    if not payload:
        print(f"❌ {host}: トークンのデコードに失敗")
        return
    
    # 有効期限（exp）を確認
    exp = payload.get('exp')
    if not exp:
        print(f"⚠️ {host}: 有効期限情報なし")
        return
    
    exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    remaining = exp_dt - now
    
    print(f"\n{'='*60}")
    print(f"ホスト: {host}")
    print(f"{'='*60}")
    print(f"トークン: {token[:30]}...")
    print(f"有効期限: {exp_dt.isoformat()}")
    print(f"現在時刻: {now.isoformat()}")
    print(f"残り時間: {remaining}")
    
    if remaining.total_seconds() > 0:
        print(f"✅ 有効")
    else:
        print(f"❌ 期限切れ（{abs(remaining)} 前）")
    
    # その他の情報
    if 'iss' in payload:
        print(f"発行者: {payload['iss']}")
    if 'sub' in payload:
        print(f"サブジェクト: {payload['sub']}")
    if 'aud' in payload:
        print(f"オーディエンス: {payload['aud']}")

if __name__ == '__main__':
    from config.common import load_all_bearer_tokens
    
    print("\n" + "="*60)
    print("RDE Bearer Token 有効性チェック")
    print("="*60)
    
    tokens = load_all_bearer_tokens()
    
    for host, token_data in tokens.items():
        # TokenManager形式の場合
        if isinstance(token_data, dict):
            access_token = token_data.get('access_token', '')
        else:
            access_token = token_data
        
        if access_token:
            check_token_expiry(access_token, host)
    
    print("\n" + "="*60)
