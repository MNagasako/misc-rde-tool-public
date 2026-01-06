from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict

from config.common import get_dynamic_file_path


def read_version_from_version_txt(version_txt_path: str | None = None) -> str:
    """VERSION.txt からバージョン文字列を取得する。"""
    path = version_txt_path or get_dynamic_file_path("VERSION.txt")
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            v = (line or "").strip()
            if v:
                return v.lstrip("v")
    raise ValueError("VERSION.txt にバージョンが見つかりません")


def compute_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def default_installer_path(version: str) -> str:
    return get_dynamic_file_path(f"setup/Output/arim_rde_tool_setup.{version}.exe")


def default_public_url(version: str) -> str:
    # 公開用リポジトリへ手動配置する前提のデフォルト（必要に応じて上書きする）
    return (
        "https://github.com/MNagasako/misc-rde-tool-public/"
        f"releases/download/v{version}/arim_rde_tool_setup.{version}.exe"
    )


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_iso_datetime(value: str) -> str:
    s = (value or "").strip()
    if not s:
        raise ValueError("updatedAt が空です")
    # 末尾Zを許容（UTC）
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def build_latest_json(*, version: str, url: str, sha256: str, updated_at: str | None = None) -> Dict[str, str]:
    v = (version or "").strip().lstrip("v")
    u = (url or "").strip()
    s = (sha256 or "").strip().lower()
    if not v:
        raise ValueError("version が空です")
    if not u:
        raise ValueError("url が空です")
    if len(s) != 64:
        raise ValueError("sha256 の形式が不正です（64桁hex）")
    ua = _normalize_iso_datetime(updated_at) if updated_at is not None else _now_utc_iso()
    return {"version": v, "url": u, "sha256": s, "updatedAt": ua}


def write_latest_json(file_path: str, payload: Dict[str, Any]) -> str:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return file_path
