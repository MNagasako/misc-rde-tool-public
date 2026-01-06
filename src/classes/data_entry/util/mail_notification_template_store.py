from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Literal, Optional

from config.common import get_dynamic_file_path

TemplateKind = Literal["individual", "combined"]


@dataclass(frozen=True)
class MailNotificationTemplateSet:
    subject: str
    header: str
    body: str
    footer: str


@dataclass(frozen=True)
class MailNotificationTemplate:
    name: str
    template: MailNotificationTemplateSet


_TEMPLATE_DIR_NAME = "mail_notification_templates"

_KIND_INDIVIDUAL: TemplateKind = "individual"
_KIND_COMBINED: TemplateKind = "combined"

_SUBJECT = "subject.txt"
_HEADER = "header.txt"
_BODY = "body.txt"
_FOOTER = "footer.txt"

# v2(旧): 1テンプレ内に individual/combined 両方を保存していた名残
_INDIVIDUAL_SUBJECT_V2 = "individual_subject.txt"
_INDIVIDUAL_HEADER_V2 = "individual_header.txt"
_INDIVIDUAL_BODY_V2 = "individual_body.txt"
_INDIVIDUAL_FOOTER_V2 = "individual_footer.txt"

_COMBINED_SUBJECT_V2 = "combined_subject.txt"
_COMBINED_HEADER_V2 = "combined_header.txt"
_COMBINED_BODY_V2 = "combined_body.txt"
_COMBINED_FOOTER_V2 = "combined_footer.txt"

_MIGRATION_MARKER = "templates_v3_migrated.marker"


def templates_root_dir(*, kind: TemplateKind) -> str:
    root = get_dynamic_file_path(os.path.join("output", "rde", "data", _TEMPLATE_DIR_NAME, str(kind)))
    os.makedirs(root, exist_ok=True)
    return root


def _legacy_templates_root_dir_v2() -> str:
    # v2のテンプレ保存先（kindサブディレクトリ無し）
    root = get_dynamic_file_path(os.path.join("output", "rde", "data", _TEMPLATE_DIR_NAME))
    os.makedirs(root, exist_ok=True)
    return root


def _migration_marker_path() -> str:
    return os.path.join(_legacy_templates_root_dir_v2(), _MIGRATION_MARKER)


def _has_migration_marker() -> bool:
    try:
        return os.path.exists(_migration_marker_path())
    except Exception:
        return False


def _write_migration_marker() -> None:
    try:
        os.makedirs(_legacy_templates_root_dir_v2(), exist_ok=True)
        with open(_migration_marker_path(), "w", encoding="utf-8", newline="\n") as f:
            f.write("migrated\n")
    except Exception:
        pass


def _safe_dir_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return ""
    # Windows/Unix共通で扱いやすい範囲に制限
    n = re.sub(r"[\\/:*?\"<>|]", "_", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _template_dir(*, kind: TemplateKind, name: str) -> str:
    safe = _safe_dir_name(name)
    if not safe:
        raise ValueError("template name is empty")
    return os.path.join(templates_root_dir(kind=kind), safe)


def list_template_names(*, kind: TemplateKind) -> List[str]:
    root = templates_root_dir(kind=kind)
    try:
        names = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
    except Exception:
        names = []
    # 安定化
    names.sort(key=lambda s: s.lower())
    return names


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text or "")


def load_template(*, kind: TemplateKind, name: str) -> MailNotificationTemplate:
    d = _template_dir(kind=kind, name=name)

    tpl = MailNotificationTemplateSet(
        subject=_read_text(os.path.join(d, _SUBJECT)).strip(),
        header=_read_text(os.path.join(d, _HEADER)),
        body=_read_text(os.path.join(d, _BODY)),
        footer=_read_text(os.path.join(d, _FOOTER)),
    )
    return MailNotificationTemplate(name=_safe_dir_name(name), template=tpl)


def save_template(*, kind: TemplateKind, template: MailNotificationTemplate) -> None:
    d = _template_dir(kind=kind, name=template.name)
    _write_text(os.path.join(d, _SUBJECT), (template.template.subject or "").strip())
    _write_text(os.path.join(d, _HEADER), template.template.header or "")
    _write_text(os.path.join(d, _BODY), template.template.body or "")
    _write_text(os.path.join(d, _FOOTER), template.template.footer or "")


def _default_template_set(*, kind: TemplateKind) -> MailNotificationTemplateSet:
    if kind == _KIND_INDIVIDUAL:
        return MailNotificationTemplateSet(
            subject="[RDE] 登録失敗: {dataName} ({entryId})",
            header="",
            body=(
                "{testNotice}\n"
                "登録状況: FAILED\n"
                "開始時刻(JST): {startTime}\n"
                "データ名: {dataName}\n"
                "データセット: {datasetName}\n"
                "データセットテンプレ: {datasetTemplateName}\n"
                "設備ID: {equipmentId}\n"
                "装置名_日: {deviceNameJa}\n"
                "エラーコード: {errorCode}\n"
                "エラーメッセージ: {errorMessage}\n"
                "投入者: {createdByName} <{createdByMail}>\n"
                "所有者: {dataOwnerName} <{dataOwnerMail}>\n"
                "設備管理者: {equipmentManagerNames} <{equipmentManagerEmails}>\n"
                "エントリID: {entryId}\n"
            ),
            footer="",
        )

    # combined
    return MailNotificationTemplateSet(
        subject="[RDE] 登録失敗: 対象件数: {count}",
        header="{testNotice}\n自動通知（{nowJst} JST）\n対象件数: {count}\n",
        body=(
            "開始時刻(JST): {startTime}\n"
            "設備ID: {equipmentId}\n"
            "装置名_日: {deviceNameJa}\n"
            "データセットテンプレ: {datasetTemplateName}\n"
            "データ名: {dataName}\n"
            "エラーコード: {errorCode}\n"
            "エラーメッセージ: {errorMessage}\n"
            "投入者: {createdByName} <{createdByMail}>\n"
            "所有者: {dataOwnerName} <{dataOwnerMail}>\n"
            "設備管理者: {equipmentManagerNames} <{equipmentManagerEmails}>\n"
            "entryId: {entryId}\n"
        ),
        footer="",
    )


def create_template(
    *,
    kind: TemplateKind,
    name: str,
    base: Optional[MailNotificationTemplateSet] = None,
) -> MailNotificationTemplate:
    safe = _safe_dir_name(name)
    if not safe:
        raise ValueError("template name is empty")

    if safe in list_template_names(kind=kind):
        raise ValueError("template already exists")

    tpl = base if base is not None else _default_template_set(kind=kind)
    t = MailNotificationTemplate(name=safe, template=tpl)
    save_template(kind=kind, template=t)
    return t


def delete_template(*, kind: TemplateKind, name: str) -> None:
    d = _template_dir(kind=kind, name=name)
    if not os.path.isdir(d):
        return

    # ディレクトリを安全に削除（テンプレは小規模）
    for root, _dirs, files in os.walk(d, topdown=False):
        for fn in files:
            try:
                os.remove(os.path.join(root, fn))
            except Exception:
                pass
        try:
            os.rmdir(root)
        except Exception:
            pass


def ensure_migrated_from_config(cfg) -> None:
    """旧 config / 旧テンプレ保存形式 から、分離テンプレ(kind別)へ移行する。"""

    try:
        migrated = bool(cfg.get("mail.notification.templates_v3_migrated", False))
    except Exception:
        migrated = False

    if migrated:
        return

    # 設定保存が失敗する環境でも再移行を防ぐため、ファイルマーカーも併用
    if _has_migration_marker():
        try:
            cfg.set("mail.notification.templates_v3_migrated", True)
            cfg.save()
        except Exception:
            pass
        return

    try:
        legacy = cfg.get("mail.notification.templates", None)
    except Exception:
        legacy = None

    if isinstance(legacy, list) and legacy:
        # 旧テンプレを1つずつ移行（subject/body を個別/統合に同値で展開）
        for idx, t in enumerate([x for x in legacy if isinstance(x, dict)]):
            name = str(t.get("name") or "").strip() or f"テンプレ{idx+1}"
            subject = str(t.get("subject") or "")
            body = str(t.get("body") or "")

            safe = _safe_dir_name(name)
            if not safe:
                continue

            for kind in (_KIND_INDIVIDUAL, _KIND_COMBINED):
                if safe in list_template_names(kind=kind):
                    continue
                create_template(
                    kind=kind,
                    name=safe,
                    base=MailNotificationTemplateSet(subject=subject, header="", body=body, footer=""),
                )

    # v2(旧保存形式)からの移行: 1テンプレ内に individual/combined 両方を持つ
    try:
        legacy_root = _legacy_templates_root_dir_v2()
        legacy_dirs = [d for d in os.listdir(legacy_root) if os.path.isdir(os.path.join(legacy_root, d))]
    except Exception:
        legacy_dirs = []

    for dname in legacy_dirs:
        d = os.path.join(_legacy_templates_root_dir_v2(), dname)
        # v2形式の目印となるファイルが無ければスキップ
        if not (
            os.path.exists(os.path.join(d, _INDIVIDUAL_SUBJECT_V2))
            or os.path.exists(os.path.join(d, _COMBINED_SUBJECT_V2))
        ):
            continue

        safe = _safe_dir_name(dname)
        if not safe:
            continue

        ind = MailNotificationTemplateSet(
            subject=_read_text(os.path.join(d, _INDIVIDUAL_SUBJECT_V2)).strip(),
            header=_read_text(os.path.join(d, _INDIVIDUAL_HEADER_V2)),
            body=_read_text(os.path.join(d, _INDIVIDUAL_BODY_V2)),
            footer=_read_text(os.path.join(d, _INDIVIDUAL_FOOTER_V2)),
        )
        cmb = MailNotificationTemplateSet(
            subject=_read_text(os.path.join(d, _COMBINED_SUBJECT_V2)).strip(),
            header=_read_text(os.path.join(d, _COMBINED_HEADER_V2)),
            body=_read_text(os.path.join(d, _COMBINED_BODY_V2)),
            footer=_read_text(os.path.join(d, _COMBINED_FOOTER_V2)),
        )

        if safe and safe not in list_template_names(kind=_KIND_INDIVIDUAL):
            create_template(kind=_KIND_INDIVIDUAL, name=safe, base=ind)
        if safe and safe not in list_template_names(kind=_KIND_COMBINED):
            create_template(kind=_KIND_COMBINED, name=safe, base=cmb)

    # 旧キーは残しつつ、以降はv3へ
    try:
        cfg.set("mail.notification.templates_v3_migrated", True)
        cfg.save()
    except Exception:
        pass

    # config保存が失敗しても再起動で復活しないよう、マーカーを残す
    _write_migration_marker()


def load_all_templates(*, kind: TemplateKind) -> List[MailNotificationTemplate]:
    names = list_template_names(kind=kind)
    if not names:
        # 初回はデフォルトを生成
        create_template(kind=kind, name="デフォルト")
        names = list_template_names(kind=kind)
    return [load_template(kind=kind, name=n) for n in names]


def format_template_name_list(names: Iterable[str]) -> str:
    ns = [str(n or "").strip() for n in names or [] if str(n or "").strip()]
    return ", ".join(ns)
