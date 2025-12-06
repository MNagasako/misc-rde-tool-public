"""
API呼び出し記録ラッパー関数

basic_info_logic.pyのAPI呼び出し箇所に記録機能を統合するための
ラッパー関数群を提供します。

各API呼び出しを記録し、APICallRecorderに自動的に追加します。
"""

import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any
from net.api_call_recorder import (
    APICallRecorder, APIRequestPayload, APIResponseResult,
    get_global_recorder
)

logger = logging.getLogger(__name__)


def record_api_call_for_self_info(
    url: str,
    headers: Dict[str, str],
    status_code: int,
    elapsed_ms: float,
    success: bool = True,
    error: Optional[str] = None
):
    """ユーザー情報取得APIをレコード"""
    recorder = get_global_recorder()
    
    request = APIRequestPayload(
        method="GET",
        url=url,
        headers=headers
    )
    
    response = APIResponseResult(
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        success=success,
        error_message=error
    )
    
    recorder.record_call(
        call_type="fetch_self_info",
        request=request,
        response=response,
        step_index=0,
        step_name="ユーザー情報取得",
        notes="RDE User API からのユーザー自身の情報取得"
    )


def record_api_call_for_group(
    url: str,
    headers: Dict[str, str],
    status_code: int,
    elapsed_ms: float,
    group_type: str = "root",
    success: bool = True,
    error: Optional[str] = None
):
    """グループ情報取得APIをレコード"""
    recorder = get_global_recorder()
    
    request = APIRequestPayload(
        method="GET",
        url=url,
        headers=headers,
        query_params={
            "include": "children,members"
        }
    )
    
    response = APIResponseResult(
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        success=success,
        error_message=error
    )
    
    # グループタイプに応じてステップ名を決定
    step_name_map = {
        "root": "グループ情報取得（Root）",
        "detail": "グループ詳細情報取得",
        "subgroup": "サブグループ情報取得"
    }
    step_name = step_name_map.get(group_type, f"グループ情報取得（{group_type}）")
    
    recorder.record_call(
        call_type="fetch_group_info",
        request=request,
        response=response,
        step_index=1,
        step_name=step_name,
        notes=f"RDE API からのグループ情報取得（タイプ: {group_type}）"
    )


def record_api_call_for_subgroup_detail(
    url: str,
    headers: Dict[str, str],
    status_code: int,
    elapsed_ms: float,
    subgroup_id: str,
    subgroup_name: str = "",
    step_index: int = 1,
    success: bool = True,
    error: Optional[str] = None
):
    """サブグループ個別詳細取得APIをレコード（v2.1.17追加）"""
    recorder = get_global_recorder()
    
    request = APIRequestPayload(
        method="GET",
        url=url,
        headers=headers,
        query_params={
            "include": "children,members"
        }
    )
    
    response = APIResponseResult(
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        success=success,
        error_message=error
    )
    
    step_name = f"サブグループ個別詳細取得 ({subgroup_name or subgroup_id[:20]}...)"
    notes = f"複数サブグループ個別取得機能: {subgroup_id}"
    
    recorder.record_call(
        call_type="fetch_subgroup_detail",
        request=request,
        response=response,
        step_index=step_index,
        step_name=step_name,
        notes=notes
    )


def record_api_call_for_organization(
    url: str,
    headers: Dict[str, str],
    status_code: int,
    elapsed_ms: float,
    success: bool = True,
    error: Optional[str] = None
):
    """組織情報取得APIをレコード"""
    recorder = get_global_recorder()
    
    request = APIRequestPayload(
        method="GET",
        url=url,
        headers=headers
    )
    
    response = APIResponseResult(
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        success=success,
        error_message=error
    )
    
    recorder.record_call(
        call_type="fetch_organization",
        request=request,
        response=response,
        step_index=2,
        step_name="組織情報取得",
        notes="RDE Instrument API からの組織情報取得"
    )


def record_api_call_for_instrument_type(
    url: str,
    headers: Dict[str, str],
    status_code: int,
    elapsed_ms: float,
    success: bool = True,
    error: Optional[str] = None
):
    """装置タイプ情報取得APIをレコード"""
    recorder = get_global_recorder()
    
    request = APIRequestPayload(
        method="GET",
        url=url,
        headers=headers,
        query_params={
            "programId": "4bbf62be-f270-4a46-9682-38cd064607ba"
        }
    )
    
    response = APIResponseResult(
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        success=success,
        error_message=error
    )
    
    recorder.record_call(
        call_type="fetch_instrument_type",
        request=request,
        response=response,
        step_index=2,
        step_name="装置タイプ情報取得",
        notes="RDE Instrument API からの装置タイプ定義取得"
    )


def record_api_call_for_dataset_list(
    url: str,
    headers: Dict[str, str],
    status_code: int,
    elapsed_ms: float,
    query_params: Optional[Dict[str, str]] = None,
    success: bool = True,
    error: Optional[str] = None
):
    """データセット一覧取得APIをレコード"""
    recorder = get_global_recorder()
    
    request = APIRequestPayload(
        method="GET",
        url=url,
        headers=headers,
        query_params=query_params or {
            "sort": "-modified",
            "page[limit]": "5000",
            "include": "manager,releases",
            "fields[user]": "id,userName,organizationName,isDeleted",
            "fields[release]": "version,releaseNumber"
        }
    )
    
    response = APIResponseResult(
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        success=success,
        error_message=error
    )
    
    recorder.record_call(
        call_type="fetch_dataset_list",
        request=request,
        response=response,
        step_index=3,
        step_name="データセット一覧取得",
        notes="RDE API からの全データセット一覧取得（ページングなし、上限5000件）"
    )


def record_api_call_for_template(
    url: str,
    headers: Dict[str, str],
    status_code: int,
    elapsed_ms: float,
    success: bool = True,
    error: Optional[str] = None
):
    """テンプレート情報取得APIをレコード"""
    recorder = get_global_recorder()
    
    request = APIRequestPayload(
        method="GET",
        url=url,
        headers=headers
    )
    
    response = APIResponseResult(
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        success=success,
        error_message=error
    )
    
    recorder.record_call(
        call_type="fetch_template",
        request=request,
        response=response,
        step_index=4,
        step_name="テンプレート情報取得",
        notes="RDE Data Entry API からのテンプレート情報取得"
    )


def record_api_call_for_instruments(
    url: str,
    headers: Dict[str, str],
    status_code: int,
    elapsed_ms: float,
    success: bool = True,
    error: Optional[str] = None
):
    """設備情報取得APIをレコード"""
    recorder = get_global_recorder()
    
    request = APIRequestPayload(
        method="GET",
        url=url,
        headers=headers
    )
    
    response = APIResponseResult(
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        success=success,
        error_message=error
    )
    
    recorder.record_call(
        call_type="fetch_instruments",
        request=request,
        response=response,
        step_index=4,
        step_name="設備情報取得",
        notes="RDE Instrument API からの設備情報取得"
    )


def record_api_call_for_licenses(
    url: str,
    headers: Dict[str, str],
    status_code: int,
    elapsed_ms: float,
    success: bool = True,
    error: Optional[str] = None
):
    """ライセンス情報取得APIをレコード"""
    recorder = get_global_recorder()
    
    request = APIRequestPayload(
        method="GET",
        url=url,
        headers=headers
    )
    
    response = APIResponseResult(
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        success=success,
        error_message=error
    )
    
    recorder.record_call(
        call_type="fetch_licenses",
        request=request,
        response=response,
        step_index=4,
        step_name="利用ライセンス情報取得",
        notes="RDE API からの利用ライセンス情報取得"
    )


# 記録機能統合の有効化フラグ
ENABLE_API_RECORDING = True


def with_api_recording(
    call_type: str,
    step_index: int,
    step_name: str,
    notes: str = ""
):
    """
    APIコール記録機能を統合するデコレータ
    
    使用例:
        @with_api_recording("fetch_dataset", 3, "データセット一覧取得")
        def fetch_dataset_list_only(bearer_token, output_dir="output/rde/data"):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not ENABLE_API_RECORDING:
                # 記録機能が無効な場合は元の関数を実行
                return func(*args, **kwargs)
            
            # API呼び出しの実行と計測
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.time() - start_time) * 1000
                
                # 成功時の記録
                recorder = get_global_recorder()
                response = APIResponseResult(
                    status_code=200,
                    elapsed_ms=elapsed_ms,
                    success=True
                )
                
                # リクエスト情報は関数内で設定されることを想定
                request = APIRequestPayload(
                    method="GET",
                    url="(記録処理中)"
                )
                
                recorder.record_call(
                    call_type=call_type,
                    request=request,
                    response=response,
                    step_index=step_index,
                    step_name=step_name,
                    notes=notes
                )
                
                return result
            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                
                # エラー時の記録
                recorder = get_global_recorder()
                response = APIResponseResult(
                    status_code=500,
                    elapsed_ms=elapsed_ms,
                    success=False,
                    error_message=str(e)
                )
                
                request = APIRequestPayload(
                    method="GET",
                    url="(エラーで中止)"
                )
                
                recorder.record_call(
                    call_type=call_type,
                    request=request,
                    response=response,
                    step_index=step_index,
                    step_name=step_name,
                    notes=f"{notes} (Error: {str(e)[:100]})"
                )
                
                raise
        
        return wrapper
    return decorator
