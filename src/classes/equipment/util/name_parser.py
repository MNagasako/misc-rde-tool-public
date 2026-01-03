from __future__ import annotations

import html as html_lib
import re
from typing import Tuple


_PAREN_PATTERN = re.compile(
    r"^(?P<ja>.*?)[\s\u00a0\u2002]*[\(\uff08](?P<en>.*?)[\)\uff09]\s*$"
)


def split_device_name_from_facility_name(value: str) -> Tuple[str, str]:
    """設備名称から装置名(日本語/英語)を分離する。

    入力は HTML実体参照（&ensp;等）や特殊空白を含む場合がある。
    既存実装互換のため、英語名が抽出できない場合は (ja, ja) を返す。
    """

    raw = str(value or "")
    # HTML実体参照をデコード（&ensp; 等）
    s = html_lib.unescape(raw)
    # 空白の揺れを正規化（nbsp/ensp 由来の文字を含む）
    s = s.replace("\u00a0", " ").replace("\u2002", " ")
    s = re.sub(r"\s+", " ", s).strip()

    if not s:
        return "", ""

    m = _PAREN_PATTERN.match(s)
    if not m:
        return s, s

    ja = (m.group("ja") or "").strip()
    en = (m.group("en") or "").strip()
    if not ja and en:
        # あり得ないが安全側
        return en, en
    if not en:
        return ja, ja
    return ja, en
