"""
API呼び出し履歴記録・再生機能モジュール

基本情報取得などの複数ステップ処理における、
各APIアクセスの詳細（ペイロード、ヘッダ、結果）を
構造化して記録し、後から確認・分析できる機能を提供します。
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum


class APICallType(Enum):
    """APIコール種別"""
    FETCH_SELF = "fetch_self_info"  # ユーザー情報取得
    FETCH_GROUP = "fetch_group_info"  # グループ情報取得
    FETCH_GROUP_DETAIL = "fetch_group_detail"  # グループ詳細取得
    FETCH_SUBGROUP = "fetch_subgroup_info"  # サブグループ取得
    FETCH_SUBGROUP_DETAIL = "fetch_subgroup_detail"  # サブグループ個別詳細取得（v2.1.17追加）
    FETCH_ORGANIZATION = "fetch_organization"  # 組織情報取得
    FETCH_INSTRUMENT_TYPE = "fetch_instrument_type"  # 装置タイプ情報取得
    FETCH_TEMPLATE = "fetch_template"  # テンプレート情報取得
    FETCH_INSTRUMENTS = "fetch_instruments"  # 設備情報取得
    FETCH_LICENSES = "fetch_licenses"  # ライセンス情報取得
    FETCH_DATASET = "fetch_dataset_list"  # データセット一覧取得
    CUSTOM = "custom"  # カスタムAPI呼び出し


@dataclass
class APIRequestPayload:
    """APIリクエストペイロード情報"""
    method: str = "GET"  # HTTPメソッド
    url: str = ""  # リクエストURL
    headers: Dict[str, str] = field(default_factory=dict)  # リクエストヘッダ
    query_params: Dict[str, Any] = field(default_factory=dict)  # クエリパラメータ
    body: Optional[str] = None  # リクエストボディ
    
    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        return asdict(self)
    
    def get_summary(self) -> str:
        """サマリー文字列を返す"""
        lines = [
            f"Method: {self.method}",
            f"URL: {self.url}",
            f"Headers ({len(self.headers)}):",
        ]
        
        # 重要なヘッダのみ表示
        important_headers = ['Authorization', 'Host', 'Origin', 'Referer', 'Content-Type']
        for key in important_headers:
            if key in self.headers:
                value = self.headers[key]
                # Authorizationトークンはマスク
                if key == 'Authorization':
                    value = value[:20] + "..." if len(value) > 20 else value
                lines.append(f"  {key}: {value}")
        
        if self.query_params:
            lines.append(f"Query Params: {json.dumps(self.query_params, ensure_ascii=False, indent=2)}")
        
        if self.body:
            try:
                body_obj = json.loads(self.body)
                lines.append(f"Body: {json.dumps(body_obj, ensure_ascii=False, indent=2)}")
            except:
                lines.append(f"Body: {self.body[:200]}...")
        
        return "\n".join(lines)


@dataclass
class APIResponseResult:
    """APIレスポンス情報"""
    status_code: int = 0  # HTTPステータスコード
    elapsed_ms: float = 0.0  # 処理時間（ミリ秒）
    response_size: int = 0  # レスポンスサイズ（バイト）
    content_type: str = ""  # Content-Type
    success: bool = True  # 成功/失敗
    error_message: Optional[str] = None  # エラーメッセージ
    
    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        return asdict(self)
    
    def get_summary(self) -> str:
        """サマリー文字列を返す"""
        lines = [
            f"Status: HTTP {self.status_code}",
            f"Elapsed: {self.elapsed_ms:.1f}ms",
            f"Response Size: {self.response_size} bytes",
            f"Content-Type: {self.content_type}",
            f"Result: {'✅ Success' if self.success else '❌ Failed'}",
        ]
        
        if self.error_message:
            lines.append(f"Error: {self.error_message}")
        
        return "\n".join(lines)


@dataclass
class APICallRecord:
    """単一APIコール記録"""
    call_type: str  # APIコール種別
    step_index: int = 0  # ステップインデックス（0から開始）
    step_name: str = ""  # ステップ名
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())  # タイムスタンプ
    request: APIRequestPayload = field(default_factory=APIRequestPayload)  # リクエスト情報
    response: APIResponseResult = field(default_factory=APIResponseResult)  # レスポンス情報
    notes: str = ""  # メモ・特記事項
    
    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        data = asdict(self)
        data['request'] = self.request.to_dict()
        data['response'] = self.response.to_dict()
        return data
    
    def get_summary(self) -> str:
        """簡潔なサマリーを返す"""
        status_icon = "✅" if self.response.success else "❌"
        return (
            f"[{self.step_index:2d}] {status_icon} {self.call_type:20s} | "
            f"{self.request.method:6s} | HTTP {self.response.status_code:3d} | "
            f"{self.response.elapsed_ms:6.1f}ms | {self.request.url}"
        )


class APICallRecorder:
    """API呼び出し履歴管理クラス"""
    
    def __init__(self, session_id: Optional[str] = None):
        """
        初期化
        
        Args:
            session_id: セッションID（未指定時は自動生成）
        """
        from datetime import datetime as dt
        self.session_id = session_id or dt.now().strftime("%Y%m%d_%H%M%S")
        self.records: List[APICallRecord] = []
        self.start_time = datetime.now()
        self.logger = logging.getLogger(__name__)
    
    def record_call(
        self,
        call_type: str,
        request: APIRequestPayload,
        response: APIResponseResult,
        step_index: int = 0,
        step_name: str = "",
        notes: str = ""
    ) -> APICallRecord:
        """
        APIコール記録を追加
        
        Args:
            call_type: APIコール種別
            request: リクエスト情報
            response: レスポンス情報
            step_index: ステップインデックス
            step_name: ステップ名
            notes: メモ
        
        Returns:
            追加された記録
        """
        record = APICallRecord(
            call_type=call_type,
            step_index=step_index,
            step_name=step_name,
            request=request,
            response=response,
            notes=notes
        )
        self.records.append(record)
        
        self.logger.debug(f"API Call Recorded: {call_type} - {request.url}")
        
        return record
    
    def get_records(self) -> List[APICallRecord]:
        """全記録を取得"""
        return self.records
    
    def get_summary(self) -> str:
        """全記録のサマリーを取得"""
        lines = [
            f"{'=' * 120}",
            f"API Call Summary - Session: {self.session_id}",
            f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Calls: {len(self.records)}",
            f"{'=' * 120}",
            ""
        ]
        
        for record in self.records:
            lines.append(record.get_summary())
        
        # 統計情報
        lines.append(f"\n{'=' * 120}")
        if self.records:
            total_time = sum(r.response.elapsed_ms for r in self.records)
            success_count = sum(1 for r in self.records if r.response.success)
            failed_count = len(self.records) - success_count
            
            lines.append(f"Total Time: {total_time:.1f}ms")
            lines.append(f"Success: {success_count}, Failed: {failed_count}")
            
            # エンドポイント別集計
            endpoint_stats: Dict[str, Dict[str, int]] = {}
            for record in self.records:
                endpoint = record.request.url.split('?')[0]  # クエリ削除
                if endpoint not in endpoint_stats:
                    endpoint_stats[endpoint] = {'count': 0, 'success': 0, 'failed': 0}
                endpoint_stats[endpoint]['count'] += 1
                if record.response.success:
                    endpoint_stats[endpoint]['success'] += 1
                else:
                    endpoint_stats[endpoint]['failed'] += 1
            
            lines.append(f"\nEndpoint Statistics:")
            for endpoint, stats in sorted(endpoint_stats.items()):
                lines.append(
                    f"  {endpoint}: "
                    f"{stats['count']} calls "
                    f"({stats['success']} success, {stats['failed']} failed)"
                )
        
        lines.append(f"{'=' * 120}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        return {
            'session_id': self.session_id,
            'start_time': self.start_time.isoformat(),
            'total_calls': len(self.records),
            'records': [r.to_dict() for r in self.records]
        }
    
    def save_to_file(self, output_path: Optional[Path] = None) -> 'Path':
        """
        JSONファイルに保存
        
        Args:
            output_path: 出力パス（未指定時は自動生成）
        
        Returns:
            保存されたファイルパス
        """
        from config.common import get_dynamic_file_path
        
        if output_path is None:
            output_dir = Path(get_dynamic_file_path('output/api_call_history'))
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"api_calls_{self.session_id}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"API Call History saved: {output_path}")
        
        return output_path
    
    def get_html_report(self) -> str:
        """
        HTML形式のレポートを生成
        
        Returns:
            HTMLコンテンツ
        """
        html_parts = [
            f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>API Call History - {self.session_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        h1 {{ color: #333; }}
        .summary {{ background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; background-color: white; }}
        th {{ background-color: #4CAF50; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .success {{ color: green; }}
        .failed {{ color: red; }}
        .details {{ margin-top: 10px; padding: 10px; background-color: #f9f9f9; border-left: 3px solid #4CAF50; }}
        pre {{ background-color: #f4f4f4; padding: 10px; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>API Call History Report</h1>
    <div class="summary">
        <p><strong>Session ID:</strong> {self.session_id}</p>
        <p><strong>Start Time:</strong> {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Total Calls:</strong> {len(self.records)}</p>
    </div>
    
    <table>
        <tr>
            <th>#</th>
            <th>Call Type</th>
            <th>Method</th>
            <th>Status</th>
            <th>Time (ms)</th>
            <th>URL</th>
        </tr>
"""
        ]
        
        for i, record in enumerate(self.records, 1):
            status_class = "success" if record.response.success else "failed"
            status_text = f"✅ {record.response.status_code}" if record.response.success else f"❌ {record.response.status_code}"
            
            html_parts.append(f"""
        <tr>
            <td>{i}</td>
            <td>{record.call_type}</td>
            <td>{record.request.method}</td>
            <td class="{status_class}">{status_text}</td>
            <td>{record.response.elapsed_ms:.1f}</td>
            <td><code>{record.request.url[:80]}...</code></td>
        </tr>
""")
        
        html_parts.append("""
    </table>
</body>
</html>
""")
        
        return "".join(html_parts)


# グローバルレコーダーインスタンス
_global_recorder: Optional[APICallRecorder] = None


def get_global_recorder(session_id: Optional[str] = None) -> APICallRecorder:
    """
    グローバルAPIコールレコーダーを取得（シングルトン）
    
    Args:
        session_id: セッションID（初期化時のみ使用）
    
    Returns:
        APICallRecorder インスタンス
    """
    global _global_recorder
    
    if _global_recorder is None:
        _global_recorder = APICallRecorder(session_id=session_id)
    
    return _global_recorder


def reset_global_recorder(session_id: Optional[str] = None):
    """
    グローバルレコーダーをリセット
    
    Args:
        session_id: 新しいセッションID
    """
    global _global_recorder
    _global_recorder = APICallRecorder(session_id=session_id)


def log_api_call(
    call_type: str,
    request: APIRequestPayload,
    response: APIResponseResult,
    step_index: int = 0,
    step_name: str = "",
    notes: str = ""
):
    """
    グローバルレコーダーにAPIコールを記録（便利関数）
    
    Args:
        call_type: APIコール種別
        request: リクエスト情報
        response: レスポンス情報
        step_index: ステップインデックス
        step_name: ステップ名
        notes: メモ
    """
    recorder = get_global_recorder()
    recorder.record_call(
        call_type=call_type,
        request=request,
        response=response,
        step_index=step_index,
        step_name=step_name,
        notes=notes
    )
