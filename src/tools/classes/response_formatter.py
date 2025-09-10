import json
from typing import Dict

class ResponseFormatter:
    """レスポンス整形・表示用ユーティリティクラス"""

    @staticmethod
    def format_response_for_display(result: Dict) -> str:
        """レスポンスを表示用に整形"""
        try:
            formatted_parts = []

            # リクエスト情報
            if 'request' in result:
                req = result['request']
                formatted_parts.append("=== REQUEST ===")
                formatted_parts.append(f"Method: {req.get('method', 'Unknown')}")
                formatted_parts.append(f"URL: {req.get('url', 'Unknown')}")

                if 'headers' in req and req['headers']:
                    formatted_parts.append("\nRequest Headers:")
                    for key, value in req['headers'].items():
                        if key.lower() == 'authorization' and value:
                            formatted_parts.append(f"  {key}: (hidden)")
                        else:
                            formatted_parts.append(f"  {key}: {value}")

                if 'data' in req and req['data']:
                    formatted_parts.append(f"\nRequest Data: {json.dumps(req['data'], indent=2, ensure_ascii=False)}")

                formatted_parts.append("")

            # レスポンス情報
            if 'response' in result:
                resp = result['response']
                formatted_parts.append("=== RESPONSE ===")
                formatted_parts.append(f"Status: {resp.get('status_code', 'Unknown')}")
                formatted_parts.append(f"URL: {resp.get('url', 'Unknown')}")

                if 'headers' in resp and resp['headers']:
                    formatted_parts.append("\nResponse Headers:")
                    for key, value in resp['headers'].items():
                        formatted_parts.append(f"  {key}: {value}")

                if 'body' in resp:
                    formatted_parts.append("\nResponse Body:")
                    body = resp['body']
                    if isinstance(body, dict):
                        formatted_parts.append(json.dumps(body, indent=2, ensure_ascii=False))
                    else:
                        formatted_parts.append(str(body))

            # エラー情報
            if 'error' in result:
                formatted_parts.append("\n=== ERROR ===")
                formatted_parts.append(str(result['error']))

            # タイムスタンプ
            if 'timestamp' in result:
                formatted_parts.append(f"\n=== TIMESTAMP ===")
                formatted_parts.append(result['timestamp'])

            return "\n".join(formatted_parts)

        except Exception as e:
            return f"フォーマット処理エラー: {e}\n\n元データ:\n{json.dumps(result, indent=2, ensure_ascii=False)}"
