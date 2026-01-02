from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from net import http_helpers


@dataclass(frozen=True)
class M365OAuthSettings:
    client_id: str
    tenant: str = "common"  # common | organizations | consumers | <tenant-id>


@dataclass(frozen=True)
class DeviceCodeInfo:
    verification_uri: str
    user_code: str
    message: str
    expires_in: int


def acquire_token_device_code(
    *,
    oauth: M365OAuthSettings,
    scopes: Optional[list[str]] = None,
) -> Tuple[str, DeviceCodeInfo]:
    """Microsoft 365 (Entra ID) のデバイスコードフローでアクセストークンを取得する。

    注意:
    - 実行時にユーザーがブラウザで認証する必要がある。
    - 本関数はトークンを永続化しない（保存は将来拡張）。

    Returns:
        (access_token, device_code_info)

    Raises:
        RuntimeError: msal未導入、または認証失敗
    """
    if scopes is None:
        # Mail.Send は Graph の delegated permission
        scopes = ["Mail.Send"]

    try:
        import msal  # type: ignore
    except Exception as e:
        raise RuntimeError(f"msal が利用できません: {e}")

    authority = f"https://login.microsoftonline.com/{oauth.tenant}"
    app = msal.PublicClientApplication(client_id=oauth.client_id, authority=authority)

    flow: Dict[str, Any] = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise RuntimeError(f"device flow の開始に失敗しました: {flow}")

    info = DeviceCodeInfo(
        verification_uri=str(flow.get("verification_uri") or flow.get("verification_url") or ""),
        user_code=str(flow.get("user_code") or ""),
        message=str(flow.get("message") or ""),
        expires_in=int(flow.get("expires_in") or 0),
    )

    result: Dict[str, Any] = app.acquire_token_by_device_flow(flow)
    token = result.get("access_token")
    if not token:
        err = result.get("error")
        desc = result.get("error_description")
        raise RuntimeError(f"M365認証失敗: {err}: {desc}")

    return (str(token), info)


def start_device_flow(
    *,
    oauth: M365OAuthSettings,
    scopes: Optional[list[str]] = None,
) -> Tuple[Any, Dict[str, Any], DeviceCodeInfo]:
    """デバイスコードフローの開始（認証コード表示まで）を行う。"""
    if scopes is None:
        scopes = ["Mail.Send"]

    try:
        import msal  # type: ignore
    except Exception as e:
        raise RuntimeError(f"msal が利用できません: {e}")

    authority = f"https://login.microsoftonline.com/{oauth.tenant}"
    app = msal.PublicClientApplication(client_id=oauth.client_id, authority=authority)

    flow: Dict[str, Any] = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise RuntimeError(f"device flow の開始に失敗しました: {flow}")

    info = DeviceCodeInfo(
        verification_uri=str(flow.get("verification_uri") or flow.get("verification_url") or ""),
        user_code=str(flow.get("user_code") or ""),
        message=str(flow.get("message") or ""),
        expires_in=int(flow.get("expires_in") or 0),
    )
    return app, flow, info


def finish_device_flow(app: Any, flow: Dict[str, Any]) -> str:
    """開始済みデバイスコードフローからトークン取得を完了する（ポーリング）。"""
    result: Dict[str, Any] = app.acquire_token_by_device_flow(flow)
    token = result.get("access_token")
    if not token:
        err = result.get("error")
        desc = result.get("error_description")
        raise RuntimeError(f"M365認証失敗: {err}: {desc}")
    return str(token)


def send_mail_via_graph(
    *,
    access_token: str,
    to_addrs: Iterable[str],
    subject: str,
    body: str,
) -> None:
    """Microsoft Graph (/me/sendMail) でメールを送信する。"""
    to_list = [a.strip() for a in to_addrs if a and a.strip()]
    if not to_list:
        raise ValueError("to_addrs is empty")

    url = "https://graph.microsoft.com/v1.0/me/sendMail"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body or ""},
            "toRecipients": [
                {"emailAddress": {"address": addr}}
                for addr in to_list
            ],
        },
        "saveToSentItems": True,
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    resp = http_helpers.proxy_post(url, json=payload, headers=headers)
    # Graph は 202 Accepted が基本
    if resp.status_code not in (200, 202):
        # text は巨大化し得るので一部のみ
        body_text = (resp.text or "").strip()
        if len(body_text) > 500:
            body_text = body_text[:500] + "..."
        raise RuntimeError(f"Graph送信失敗: {resp.status_code} {body_text}")
