from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Iterable

import smtplib
import ssl


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    use_ssl: bool = True
    use_starttls: bool = False
    timeout_sec: int = 30


def send_email_via_smtp(
    *,
    smtp: SmtpSettings,
    username: str,
    password: str,
    from_addr: str,
    from_name: str | None = None,
    to_addrs: Iterable[str],
    subject: str,
    body: str,
) -> None:
    to_list = [a.strip() for a in to_addrs if a and a.strip()]
    if not to_list:
        raise ValueError("to_addrs is empty")

    from_name = (from_name or "").strip() or None

    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_addr)) if from_name else from_addr
    msg["To"] = ", ".join(to_list)
    msg["Subject"] = subject
    msg.set_content(body or "")

    if smtp.use_ssl:
        with smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=smtp.timeout_sec) as client:
            client.login(username, password)
            client.send_message(msg)
        return

    with smtplib.SMTP(smtp.host, smtp.port, timeout=smtp.timeout_sec) as client:
        client.ehlo()
        if smtp.use_starttls:
            context = ssl.create_default_context()
            client.starttls(context=context)
            client.ehlo()
        client.login(username, password)
        client.send_message(msg)


def get_gmail_smtp_settings() -> SmtpSettings:
    # Gmail: app password + SSL(465) をデフォルトにする
    return SmtpSettings(host="smtp.gmail.com", port=465, use_ssl=True, use_starttls=False)
