from __future__ import annotations

import logging

from classes.core.email_sender import SmtpSettings, get_gmail_smtp_settings, send_email_via_smtp
from classes.core import secret_store
from classes.managers.app_config_manager import get_config_manager

logger = logging.getLogger(__name__)


def _get_provider() -> str:
    cfg = get_config_manager()
    return str(cfg.get("mail.provider", "gmail"))


def _send_via_gmail(*, from_addr: str, to_addr: str, subject: str, body: str) -> None:
    if not from_addr:
        raise ValueError("gmail from_address is empty")

    # パスワードは設定JSONに保存しない（OSキーチェーン）
    password = secret_store.load_secret(namespace="mail:gmail", key=from_addr) or ""
    if not password:
        raise RuntimeError("Gmail アプリパスワードが未設定です（設定タブで保存してください）")

    cfg = get_config_manager()
    from_name = str(cfg.get("mail.gmail.from_name", "") or "").strip()

    send_email_via_smtp(
        smtp=get_gmail_smtp_settings(),
        username=from_addr,
        password=password,
        from_addr=from_addr,
        from_name=from_name,
        to_addrs=[to_addr],
        subject=subject,
        body=body,
    )


def _send_via_smtp(*, to_addr: str, subject: str, body: str) -> None:
    cfg = get_config_manager()
    host = str(cfg.get("mail.smtp.host", "")).strip()
    port = int(cfg.get("mail.smtp.port", 465) or 465)
    security = str(cfg.get("mail.smtp.security", "ssl"))
    username = str(cfg.get("mail.smtp.username", "")).strip()
    from_addr = str(cfg.get("mail.smtp.from_address", "")).strip()
    from_name = str(cfg.get("mail.smtp.from_name", "") or "").strip()

    if not host or not username or not from_addr:
        raise RuntimeError("SMTP設定が不足しています（host/username/from）")

    key = f"{host}:{port}:{username}"
    password = secret_store.load_secret(namespace="mail:smtp", key=key) or ""
    if not password:
        raise RuntimeError("SMTPパスワードが未設定です（設定タブで保存してください）")

    smtp = SmtpSettings(
        host=host,
        port=port,
        use_ssl=(security == "ssl"),
        use_starttls=(security == "starttls"),
    )

    send_email_via_smtp(
        smtp=smtp,
        username=username,
        password=password,
        from_addr=from_addr,
        from_name=from_name,
        to_addrs=[to_addr],
        subject=subject,
        body=body,
    )


def send_using_app_mail_settings(*, to_addr: str, subject: str, body: str) -> None:
    """設定タブの mail.* を使って送信する（Gmail/SMTP 対応）。"""
    provider = _get_provider()

    if provider == "gmail":
        cfg = get_config_manager()
        from_addr = str(cfg.get("mail.gmail.from_address", "")).strip()
        _send_via_gmail(from_addr=from_addr, to_addr=to_addr, subject=subject, body=body)
        return

    if provider == "smtp":
        _send_via_smtp(to_addr=to_addr, subject=subject, body=body)
        return

    if provider == "microsoft365":
        # 既存UIはトークンを永続化していないため、現状は通知用途で利用不可。
        raise RuntimeError("Microsoft365送信は通知用途では未対応（アクセストークン永続化が未実装）")

    raise RuntimeError(f"Unsupported mail provider: {provider}")
