from __future__ import annotations

import logging
from dataclasses import dataclass

try:
    from qt_compat.widgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QGroupBox,
        QComboBox,
        QTextEdit,
        QCheckBox,
    )
except Exception:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QGroupBox,
        QComboBox,
        QTextEdit,
        QCheckBox,
    )

from classes.core.email_sender import get_gmail_smtp_settings, send_email_via_smtp
from classes.core.email_sender import SmtpSettings
from classes.core import m365_mail_sender
from classes.core import secret_store
from classes.managers.app_config_manager import get_config_manager
from classes.theme import ThemeKey, get_color

logger = logging.getLogger(__name__)


_PROVIDER_GMAIL = "gmail"
_PROVIDER_M365 = "microsoft365"
_PROVIDER_SMTP = "smtp"


_SMTP_SECURITY_SSL = "ssl"
_SMTP_SECURITY_STARTTLS = "starttls"
_SMTP_SECURITY_NONE = "none"


@dataclass(frozen=True)
class _SmtpSecretKey:
    host: str
    port: int
    username: str

    def as_key(self) -> str:
        return f"{self.host}:{self.port}:{self.username}"


class MailSettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel("メール")
        layout.addWidget(title)

        provider_group = QGroupBox("送信方式")
        provider_layout = QHBoxLayout(provider_group)
        provider_layout.addWidget(QLabel("プロバイダ:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Gmail（アプリパスワード）", _PROVIDER_GMAIL)
        self.provider_combo.addItem("Microsoft 365（OAuth）※準備中", _PROVIDER_M365)
        self.provider_combo.addItem("汎用SMTP", _PROVIDER_SMTP)
        self.provider_combo.currentIndexChanged.connect(self._refresh_provider_ui)
        provider_layout.addWidget(self.provider_combo)
        provider_layout.addStretch()
        layout.addWidget(provider_group)

        gmail_group = QGroupBox("Gmail設定")
        gmail_layout = QVBoxLayout(gmail_group)

        row_from = QHBoxLayout()
        row_from.addWidget(QLabel("送信元（From）:"))
        self.gmail_from_edit = QLineEdit()
        self.gmail_from_edit.setPlaceholderText("例: your.name@gmail.com")
        row_from.addWidget(self.gmail_from_edit)
        gmail_layout.addLayout(row_from)

        row_from_name = QHBoxLayout()
        row_from_name.addWidget(QLabel("送信者名（任意）:"))
        self.gmail_from_name_edit = QLineEdit()
        self.gmail_from_name_edit.setPlaceholderText("例: 山田 太郎")
        row_from_name.addWidget(self.gmail_from_name_edit)
        gmail_layout.addLayout(row_from_name)

        row_pass = QHBoxLayout()
        row_pass.addWidget(QLabel("アプリパスワード:"))
        self.gmail_app_password_edit = QLineEdit()
        try:
            self.gmail_app_password_edit.setEchoMode(QLineEdit.Password)
        except Exception:
            pass
        self.gmail_app_password_edit.setPlaceholderText("16桁のアプリパスワード（保存は任意）")
        row_pass.addWidget(self.gmail_app_password_edit)
        gmail_layout.addLayout(row_pass)

        self.remember_password_checkbox = QCheckBox("OSキーチェーンに保存（推奨）")
        gmail_layout.addWidget(self.remember_password_checkbox)

        self.gmail_hint = QLabel(
            "※ Gmailは2段階認証を有効化し、Googleアカウントでアプリパスワードを発行してください。"
        )
        self.gmail_hint.setWordWrap(True)
        gmail_layout.addWidget(self.gmail_hint)

        layout.addWidget(gmail_group)

        m365_group = QGroupBox("Microsoft 365 設定")
        m365_layout = QVBoxLayout(m365_group)

        row_client = QHBoxLayout()
        row_client.addWidget(QLabel("Client ID:"))
        self.m365_client_id_edit = QLineEdit()
        self.m365_client_id_edit.setPlaceholderText("例: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        row_client.addWidget(self.m365_client_id_edit)
        m365_layout.addLayout(row_client)

        row_tenant = QHBoxLayout()
        row_tenant.addWidget(QLabel("Tenant:"))
        self.m365_tenant_edit = QLineEdit()
        self.m365_tenant_edit.setPlaceholderText("common / organizations / <tenant-id>")
        row_tenant.addWidget(self.m365_tenant_edit)
        m365_layout.addLayout(row_tenant)

        row_auth = QHBoxLayout()
        self.m365_start_auth_btn = QPushButton("認証コードを発行")
        self.m365_start_auth_btn.clicked.connect(self._start_m365_device_flow)
        row_auth.addWidget(self.m365_start_auth_btn)

        self.m365_finish_auth_btn = QPushButton("トークン取得")
        self.m365_finish_auth_btn.clicked.connect(self._finish_m365_device_flow)
        row_auth.addWidget(self.m365_finish_auth_btn)
        row_auth.addStretch()
        m365_layout.addLayout(row_auth)

        self.m365_hint = QLabel(
            "※ 手順: 1)『認証コードを発行』→ 2) 表示されたURLでユーザーコード入力 → 3)『トークン取得』。"
        )
        self.m365_hint.setWordWrap(True)
        m365_layout.addWidget(self.m365_hint)

        layout.addWidget(m365_group)

        smtp_group = QGroupBox("汎用SMTP設定")
        smtp_layout = QVBoxLayout(smtp_group)

        row_host = QHBoxLayout()
        row_host.addWidget(QLabel("Host:"))
        self.smtp_host_edit = QLineEdit()
        self.smtp_host_edit.setPlaceholderText("例: smtp.example.com")
        row_host.addWidget(self.smtp_host_edit)
        smtp_layout.addLayout(row_host)

        row_port = QHBoxLayout()
        row_port.addWidget(QLabel("Port:"))
        self.smtp_port_edit = QLineEdit()
        self.smtp_port_edit.setPlaceholderText("例: 465")
        row_port.addWidget(self.smtp_port_edit)
        smtp_layout.addLayout(row_port)

        row_sec = QHBoxLayout()
        row_sec.addWidget(QLabel("Security:"))
        self.smtp_security_combo = QComboBox()
        self.smtp_security_combo.addItem("SSL (465)", _SMTP_SECURITY_SSL)
        self.smtp_security_combo.addItem("STARTTLS (587)", _SMTP_SECURITY_STARTTLS)
        self.smtp_security_combo.addItem("なし", _SMTP_SECURITY_NONE)
        row_sec.addWidget(self.smtp_security_combo)
        row_sec.addStretch()
        smtp_layout.addLayout(row_sec)

        row_user = QHBoxLayout()
        row_user.addWidget(QLabel("Username:"))
        self.smtp_username_edit = QLineEdit()
        self.smtp_username_edit.setPlaceholderText("例: user@example.com")
        row_user.addWidget(self.smtp_username_edit)
        smtp_layout.addLayout(row_user)

        row_pass2 = QHBoxLayout()
        row_pass2.addWidget(QLabel("Password:"))
        self.smtp_password_edit = QLineEdit()
        try:
            self.smtp_password_edit.setEchoMode(QLineEdit.Password)
        except Exception:
            pass
        self.smtp_password_edit.setPlaceholderText("保存は任意（OSキーチェーン推奨）")
        row_pass2.addWidget(self.smtp_password_edit)
        smtp_layout.addLayout(row_pass2)

        self.smtp_remember_password_checkbox = QCheckBox("OSキーチェーンに保存（推奨）")
        smtp_layout.addWidget(self.smtp_remember_password_checkbox)

        row_from2 = QHBoxLayout()
        row_from2.addWidget(QLabel("From:"))
        self.smtp_from_edit = QLineEdit()
        self.smtp_from_edit.setPlaceholderText("例: user@example.com")
        row_from2.addWidget(self.smtp_from_edit)
        smtp_layout.addLayout(row_from2)

        row_from2_name = QHBoxLayout()
        row_from2_name.addWidget(QLabel("From名（任意）:"))
        self.smtp_from_name_edit = QLineEdit()
        self.smtp_from_name_edit.setPlaceholderText("例: ARIM RDE Tool")
        row_from2_name.addWidget(self.smtp_from_name_edit)
        smtp_layout.addLayout(row_from2_name)

        layout.addWidget(smtp_group)

        test_group = QGroupBox("テストメール")
        test_layout = QVBoxLayout(test_group)

        row_to = QHBoxLayout()
        row_to.addWidget(QLabel("送信先（To）:"))
        self.test_to_edit = QLineEdit()
        self.test_to_edit.setPlaceholderText("例: your.name@gmail.com")
        row_to.addWidget(self.test_to_edit)
        test_layout.addLayout(row_to)

        row_subject = QHBoxLayout()
        row_subject.addWidget(QLabel("件名:"))
        self.test_subject_edit = QLineEdit()
        self.test_subject_edit.setPlaceholderText("例: ARIM RDE Tool テストメール")
        row_subject.addWidget(self.test_subject_edit)
        test_layout.addLayout(row_subject)

        self.test_body_edit = QTextEdit()
        self.test_body_edit.setPlaceholderText("本文（自由編集）")
        test_layout.addWidget(self.test_body_edit)

        btn_row = QHBoxLayout()
        self.send_test_btn = QPushButton("テストメール送信")
        self.send_test_btn.clicked.connect(self._send_test_mail)
        btn_row.addWidget(self.send_test_btn)
        btn_row.addStretch()
        test_layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        test_layout.addWidget(self.status_label)

        layout.addWidget(test_group)
        layout.addStretch()

        self._m365_msal_app = None
        self._m365_device_flow = None
        self._m365_access_token: str | None = None

        self._refresh_provider_ui()
        self.load_current_settings()

    def _refresh_provider_ui(self):
        provider = self._provider()
        is_gmail = provider == _PROVIDER_GMAIL
        is_m365 = provider == _PROVIDER_M365
        is_smtp = provider == _PROVIDER_SMTP

        self.gmail_from_edit.setEnabled(is_gmail)
        self.gmail_from_name_edit.setEnabled(is_gmail)
        self.gmail_app_password_edit.setEnabled(is_gmail)
        self.remember_password_checkbox.setEnabled(is_gmail)
        self.send_test_btn.setEnabled(is_gmail or is_m365 or is_smtp)

        self.m365_client_id_edit.setEnabled(is_m365)
        self.m365_tenant_edit.setEnabled(is_m365)
        self.m365_start_auth_btn.setEnabled(is_m365)
        self.m365_finish_auth_btn.setEnabled(is_m365)

        self.smtp_host_edit.setEnabled(is_smtp)
        self.smtp_port_edit.setEnabled(is_smtp)
        self.smtp_security_combo.setEnabled(is_smtp)
        self.smtp_username_edit.setEnabled(is_smtp)
        self.smtp_password_edit.setEnabled(is_smtp)
        self.smtp_remember_password_checkbox.setEnabled(is_smtp)
        self.smtp_from_edit.setEnabled(is_smtp)
        self.smtp_from_name_edit.setEnabled(is_smtp)

        self._set_status("", None)

    def _provider(self) -> str:
        return str(self.provider_combo.currentData())

    def _set_status(self, message: str, theme_key: ThemeKey | None):
        self.status_label.setText(message)
        if theme_key is None:
            self.status_label.setStyleSheet("")
        else:
            self.status_label.setStyleSheet(f"color: {get_color(theme_key)}; font-weight: bold;")

    def load_current_settings(self):
        cfg = get_config_manager()
        provider = cfg.get("mail.provider", _PROVIDER_GMAIL)

        idx = self.provider_combo.findData(provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)

        self.gmail_from_edit.setText(cfg.get("mail.gmail.from_address", ""))
        self.gmail_from_name_edit.setText(cfg.get("mail.gmail.from_name", ""))
        self.remember_password_checkbox.setChecked(bool(cfg.get("mail.gmail.remember_app_password", False)))

        self.m365_client_id_edit.setText(cfg.get("mail.microsoft365.client_id", ""))
        self.m365_tenant_edit.setText(cfg.get("mail.microsoft365.tenant", "common"))

        self.smtp_host_edit.setText(cfg.get("mail.smtp.host", ""))
        self.smtp_port_edit.setText(str(cfg.get("mail.smtp.port", "")) if cfg.get("mail.smtp.port", "") != "" else "")
        sec = cfg.get("mail.smtp.security", _SMTP_SECURITY_SSL)
        sec_idx = self.smtp_security_combo.findData(sec)
        if sec_idx >= 0:
            self.smtp_security_combo.setCurrentIndex(sec_idx)
        self.smtp_username_edit.setText(cfg.get("mail.smtp.username", ""))
        self.smtp_from_edit.setText(cfg.get("mail.smtp.from_address", ""))
        self.smtp_from_name_edit.setText(cfg.get("mail.smtp.from_name", ""))
        self.smtp_remember_password_checkbox.setChecked(bool(cfg.get("mail.smtp.remember_password", False)))

        self.test_to_edit.setText(cfg.get("mail.test.to_address", ""))
        self.test_subject_edit.setText(cfg.get("mail.test.subject", "ARIM RDE Tool テストメール"))
        self.test_body_edit.setPlainText(cfg.get("mail.test.body", "これは ARIM RDE Tool のテストメールです。"))

        self._refresh_provider_ui()

    def save_settings(self):
        cfg = get_config_manager()

        provider = self._provider()
        cfg.set("mail.provider", provider)

        if provider == _PROVIDER_GMAIL:
            from_addr = self.gmail_from_edit.text().strip()
            cfg.set("mail.gmail.from_address", from_addr)
            cfg.set("mail.gmail.from_name", self.gmail_from_name_edit.text().strip())
            cfg.set("mail.gmail.remember_app_password", bool(self.remember_password_checkbox.isChecked()))

        if provider == _PROVIDER_M365:
            cfg.set("mail.microsoft365.client_id", self.m365_client_id_edit.text().strip())
            cfg.set("mail.microsoft365.tenant", self.m365_tenant_edit.text().strip() or "common")

        if provider == _PROVIDER_SMTP:
            cfg.set("mail.smtp.host", self.smtp_host_edit.text().strip())
            cfg.set("mail.smtp.security", str(self.smtp_security_combo.currentData()))
            cfg.set("mail.smtp.username", self.smtp_username_edit.text().strip())
            cfg.set("mail.smtp.from_address", self.smtp_from_edit.text().strip())
            cfg.set("mail.smtp.from_name", self.smtp_from_name_edit.text().strip())
            cfg.set("mail.smtp.remember_password", bool(self.smtp_remember_password_checkbox.isChecked()))
            port = self._parse_smtp_port_or_default()
            cfg.set("mail.smtp.port", port)

        cfg.set("mail.test.to_address", self.test_to_edit.text().strip())
        cfg.set("mail.test.subject", self.test_subject_edit.text().strip())
        cfg.set("mail.test.body", self.test_body_edit.toPlainText())

        cfg.save()

        if provider == _PROVIDER_GMAIL:
            self._persist_gmail_secret_if_needed()
        if provider == _PROVIDER_SMTP:
            self._persist_smtp_secret_if_needed()

    def _parse_smtp_port_or_default(self) -> int:
        raw = self.smtp_port_edit.text().strip()
        if raw:
            try:
                return int(raw)
            except Exception:
                pass

        sec = str(self.smtp_security_combo.currentData())
        if sec == _SMTP_SECURITY_STARTTLS:
            return 587
        if sec == _SMTP_SECURITY_NONE:
            return 25
        return 465

    def _persist_gmail_secret_if_needed(self):
        from_addr = self.gmail_from_edit.text().strip()
        if not from_addr:
            return

        remember = bool(self.remember_password_checkbox.isChecked())
        if not remember:
            # 明示的に保存しない場合は、残存を避けるため削除を試行
            secret_store.delete_secret(namespace="mail:gmail", key=from_addr)
            return

        if not secret_store.is_keyring_available():
            self._set_status("OSキーチェーンが利用できないため、パスワードは保存されません。", ThemeKey.TEXT_WARNING)
            return

        password = self.gmail_app_password_edit.text().strip()
        if not password:
            # パスワード欄が空なら保存しない（既存の保存値を維持）
            return

        ok = secret_store.save_secret(namespace="mail:gmail", key=from_addr, secret=password)
        if not ok:
            self._set_status("パスワード保存に失敗しました（OSキーチェーン）。", ThemeKey.TEXT_WARNING)

    def _resolve_gmail_password(self, from_addr: str) -> str:
        typed = self.gmail_app_password_edit.text().strip()
        if typed:
            return typed

        remember = bool(self.remember_password_checkbox.isChecked())
        if not remember:
            return ""

        return secret_store.load_secret(namespace="mail:gmail", key=from_addr) or ""

    def _smtp_secret_key(self) -> _SmtpSecretKey | None:
        host = self.smtp_host_edit.text().strip()
        port = self._parse_smtp_port_or_default()
        username = self.smtp_username_edit.text().strip()
        if not host or not username:
            return None
        return _SmtpSecretKey(host=host, port=port, username=username)

    def _persist_smtp_secret_if_needed(self):
        key = self._smtp_secret_key()
        if key is None:
            return

        remember = bool(self.smtp_remember_password_checkbox.isChecked())
        if not remember:
            secret_store.delete_secret(namespace="mail:smtp", key=key.as_key())
            return

        if not secret_store.is_keyring_available():
            self._set_status("OSキーチェーンが利用できないため、SMTPパスワードは保存されません。", ThemeKey.TEXT_WARNING)
            return

        password = self.smtp_password_edit.text().strip()
        if not password:
            return

        ok = secret_store.save_secret(namespace="mail:smtp", key=key.as_key(), secret=password)
        if not ok:
            self._set_status("SMTPパスワード保存に失敗しました（OSキーチェーン）。", ThemeKey.TEXT_WARNING)

    def _resolve_smtp_password(self) -> str:
        typed = self.smtp_password_edit.text().strip()
        if typed:
            return typed

        remember = bool(self.smtp_remember_password_checkbox.isChecked())
        if not remember:
            return ""

        key = self._smtp_secret_key()
        if key is None:
            return ""

        return secret_store.load_secret(namespace="mail:smtp", key=key.as_key()) or ""

    def _start_m365_device_flow(self):
        client_id = self.m365_client_id_edit.text().strip()
        tenant = self.m365_tenant_edit.text().strip() or "common"
        if not client_id:
            self._set_status("Client ID を入力してください。", ThemeKey.TEXT_WARNING)
            return

        try:
            app, flow, info = m365_mail_sender.start_device_flow(
                oauth=m365_mail_sender.M365OAuthSettings(client_id=client_id, tenant=tenant)
            )
        except Exception as e:
            self._set_status(f"Device Code開始失敗: {e}", ThemeKey.TEXT_ERROR)
            return

        self._m365_msal_app = app
        self._m365_device_flow = flow
        self._m365_access_token = None

        self._set_status(info.message or f"{info.verification_uri} で {info.user_code} を入力してください。", ThemeKey.TEXT_INFO)

        try:
            self.save_settings()
        except Exception as e:
            logger.debug("M365設定の保存に失敗: %s", e)

    def _finish_m365_device_flow(self):
        if self._m365_msal_app is None or self._m365_device_flow is None:
            self._set_status("先に『認証コードを発行』を実行してください。", ThemeKey.TEXT_WARNING)
            return

        self._set_status("トークン取得中...", ThemeKey.TEXT_INFO)
        try:
            token = m365_mail_sender.finish_device_flow(self._m365_msal_app, self._m365_device_flow)
            self._m365_access_token = token
            self._set_status("トークン取得に成功しました。テストメール送信を実行できます。", ThemeKey.TEXT_SUCCESS)
        except Exception as e:
            self._set_status(f"トークン取得失敗: {e}", ThemeKey.TEXT_ERROR)

    def _send_test_mail(self):
        provider = self._provider()

        to_addr = self.test_to_edit.text().strip()
        subject = self.test_subject_edit.text().strip()
        body = self.test_body_edit.toPlainText()

        if not to_addr:
            self._set_status("To を入力してください。", ThemeKey.TEXT_WARNING)
            return

        # 先に設定を保存（機微情報は別扱い）
        try:
            self.save_settings()
        except Exception as e:
            logger.debug("メール設定の保存に失敗: %s", e)

        self.send_test_btn.setEnabled(False)
        self._set_status("送信中...", ThemeKey.TEXT_INFO)
        try:
            if provider == _PROVIDER_GMAIL:
                from_addr = self.gmail_from_edit.text().strip()
                from_name = self.gmail_from_name_edit.text().strip()
                if not from_addr:
                    self._set_status("From を入力してください。", ThemeKey.TEXT_WARNING)
                    return

                password = self._resolve_gmail_password(from_addr)
                if not password:
                    self._set_status("アプリパスワードを入力するか、保存を有効化してください。", ThemeKey.TEXT_WARNING)
                    return

                send_email_via_smtp(
                    smtp=get_gmail_smtp_settings(),
                    username=from_addr,
                    password=password,
                    from_addr=from_addr,
                    from_name=from_name,
                    to_addrs=[to_addr],
                    subject=subject or "(no subject)",
                    body=body,
                )
                self._set_status("送信しました。", ThemeKey.TEXT_SUCCESS)
                return

            if provider == _PROVIDER_SMTP:
                host = self.smtp_host_edit.text().strip()
                port = self._parse_smtp_port_or_default()
                sec = str(self.smtp_security_combo.currentData())
                username = self.smtp_username_edit.text().strip()
                from_addr = self.smtp_from_edit.text().strip()
                from_name = self.smtp_from_name_edit.text().strip()
                if not host or not username or not from_addr:
                    self._set_status("Host/Username/From を入力してください。", ThemeKey.TEXT_WARNING)
                    return

                password = self._resolve_smtp_password()
                if not password:
                    self._set_status("SMTPパスワードを入力するか、保存を有効化してください。", ThemeKey.TEXT_WARNING)
                    return

                smtp = SmtpSettings(
                    host=host,
                    port=port,
                    use_ssl=(sec == _SMTP_SECURITY_SSL),
                    use_starttls=(sec == _SMTP_SECURITY_STARTTLS),
                )

                send_email_via_smtp(
                    smtp=smtp,
                    username=username,
                    password=password,
                    from_addr=from_addr,
                    from_name=from_name,
                    to_addrs=[to_addr],
                    subject=subject or "(no subject)",
                    body=body,
                )
                self._set_status("送信しました。", ThemeKey.TEXT_SUCCESS)
                return

            if provider == _PROVIDER_M365:
                if not self._m365_access_token:
                    self._set_status("先にM365のトークン取得を実行してください。", ThemeKey.TEXT_WARNING)
                    return

                m365_mail_sender.send_mail_via_graph(
                    access_token=self._m365_access_token,
                    to_addrs=[to_addr],
                    subject=subject or "(no subject)",
                    body=body,
                )
                self._set_status("送信しました。", ThemeKey.TEXT_SUCCESS)
                return

            self._set_status("未対応の送信方式です。", ThemeKey.TEXT_WARNING)
        except Exception as e:
            self._set_status(f"送信失敗: {e}", ThemeKey.TEXT_ERROR)
        finally:
            self.send_test_btn.setEnabled(True)
