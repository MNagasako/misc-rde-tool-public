from __future__ import annotations

import json
import math
from dataclasses import dataclass
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from classes.data_portal.util.public_output_paths import get_public_data_portal_cache_dir, get_public_data_portal_root_dir
from net.http_helpers import proxy_get, proxy_post

PROD_BASE = "https://nanonet.go.jp/data_service/arim_data.php"
TEST_BASE = "https://dq5rggbsr2dkt.cloudfront.net/test.nanonet.go.jp/data_service/arim_data.php"

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]
DetailItemCallback = Callable[["PublicArimDataDetail", int, int], None]


_PUBLIC_OUTPUT_DATASET_ID_CACHE: dict[str, object] = {
    "path": None,
    "mtime": None,
    "dataset_ids": set(),
}

_PUBLIC_LISTING_DATASET_ID_CACHE: dict[tuple[str, int, int], dict[str, object]] = {}


def get_public_published_dataset_ids(*, environment: str = "production", use_cache: bool = True) -> set[str]:
    """Return dataset_id set from public (no-login) portal `output.json`.

    This is used as a best-effort fallback when portal status cannot be resolved
    via logged-in access (e.g., no permission).
    """

    path = get_public_data_portal_root_dir(environment) / "output.json"
    cache_path = _PUBLIC_OUTPUT_DATASET_ID_CACHE.get("path")
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return set()

    if use_cache and cache_path == str(path) and _PUBLIC_OUTPUT_DATASET_ID_CACHE.get("mtime") == mtime:
        cached = _PUBLIC_OUTPUT_DATASET_ID_CACHE.get("dataset_ids")
        return set(cached) if isinstance(cached, set) else set()

    dataset_ids: set[str] = set()
    payload = None
    loaded_ok = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        loaded_ok = True
    except Exception:
        # Do not poison the cache with an empty result when parsing fails.
        # This can happen if output.json is being written while the app starts.
        cached = _PUBLIC_OUTPUT_DATASET_ID_CACHE.get("dataset_ids")
        if use_cache and cache_path == str(path) and isinstance(cached, set) and cached:
            return set(cached)
        return set()

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            dsid = str(fields.get("dataset_id") or "").strip()
            if not dsid:
                fields_raw = item.get("fields_raw") if isinstance(item.get("fields_raw"), dict) else {}
                dsid = str(fields_raw.get("dataset_id") or "").strip()
            if not dsid:
                # safety net for older payload shapes
                dsid = str(item.get("dataset_id") or "").strip()
            if dsid:
                dataset_ids.add(dsid)

    # If payload shape is unexpected, keep prior cache when available.
    if not isinstance(payload, list):
        cached = _PUBLIC_OUTPUT_DATASET_ID_CACHE.get("dataset_ids")
        if use_cache and cache_path == str(path) and isinstance(cached, set) and cached:
            return set(cached)
        return set()

    if not loaded_ok:
        return set()

    _PUBLIC_OUTPUT_DATASET_ID_CACHE["path"] = str(path)
    _PUBLIC_OUTPUT_DATASET_ID_CACHE["mtime"] = mtime
    _PUBLIC_OUTPUT_DATASET_ID_CACHE["dataset_ids"] = dataset_ids
    return set(dataset_ids)


def _with_display_params(search_url: str, *, display_result: int, display_order: int) -> str:
    parsed = urlparse(search_url)
    query = parse_qs(parsed.query)
    query["display_result"] = [str(display_result)]
    query["display_order"] = [str(display_order)]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _page_size_from_display_result(display_result: int) -> int:
    # 観測値: display_result=3 は 200件、display_result=2 は 100件。
    if display_result == 3:
        return 200
    if display_result == 2:
        return 100
    return 20


def get_public_listing_dataset_ids(
    *,
    environment: str = "production",
    timeout: int = 30,
    display_result: int = 3,
    display_order: int = 0,
    max_age_sec: int = 300,
    force_refresh: bool = False,
    page_max_workers: int = 1,
    basic_auth: Optional[tuple[str, str]] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> set[str]:
    """公開データセット一覧（ページネーション）を全件取得し、dataset_id集合を返す。

    注意:
    - 一覧ページから抽出できるIDは `code`（detail URL の `code`）を dataset_id として扱う。
    - 取得結果は TTL キャッシュし、過剰アクセスを抑止する。
    """

    env = str(environment or "production").strip() or "production"
    cache_key = (env, int(display_result), int(display_order))
    now = time.time()

    cache = _PUBLIC_LISTING_DATASET_ID_CACHE.get(cache_key)
    if not force_refresh and isinstance(cache, dict):
        fetched_at = float(cache.get("fetched_at", 0.0) or 0.0)
        dataset_ids = cache.get("dataset_ids")
        if isinstance(dataset_ids, set) and (now - fetched_at) < max(0, int(max_age_sec)):
            return set(dataset_ids)

    links = search_public_arim_data(
        keyword="",
        environment=env,
        timeout=timeout,
        display_result=display_result,
        display_order=display_order,
        max_pages=None,
        start_page=1,
        end_page=None,
        page_max_workers=max(1, int(page_max_workers or 1)),
        basic_auth=basic_auth,
        progress_callback=progress_callback,
    )

    dataset_ids: set[str] = set()
    for link in links:
        code = str(getattr(link, "code", "") or "").strip()
        if code:
            dataset_ids.add(code)

    _PUBLIC_LISTING_DATASET_ID_CACHE[cache_key] = {
        "fetched_at": now,
        "dataset_ids": set(dataset_ids),
    }

    logger.info(
        "公開一覧ID取得: env=%s display_result=%s page_size=%s ids=%s (ttl=%ss)",
        env,
        display_result,
        _page_size_from_display_result(display_result),
        len(dataset_ids),
        max(0, int(max_age_sec)),
    )

    return set(dataset_ids)


def migrate_public_data_portal_cache_dir(
    *,
    environment: str = "production",
    progress_callback: Optional[ProgressCallback] = None,
) -> tuple[int, int]:
    """公開データポータルのキャッシュJSONを新スキーマへ移行する。

    - 旧: fields_raw/data_metrics_raw/data_index_raw が list[{label,value}]
    - 新: *_raw は dict[english_key, value]

    戻り値: (migrated_count, failed_count)
    """

    cache_dir = get_public_data_portal_cache_dir(environment)
    paths = sorted(cache_dir.glob("*.json"))
    migrated = 0
    failed = 0

    total = len(paths)
    for idx, path in enumerate(paths, start=1):
        if progress_callback is not None:
            try:
                progress_callback(idx, total, f"キャッシュ移行中: {idx}/{total}")
            except Exception:
                pass

        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                continue

            changed = False
            for raw_key in ("fields_raw", "data_metrics_raw", "data_index_raw"):
                raw_val = payload.get(raw_key)
                if isinstance(raw_val, dict):
                    continue

                if isinstance(raw_val, list):
                    jp = {str(i.get("label")): str(i.get("value")) for i in raw_val if isinstance(i, dict)}
                    _, raw_en = _normalize_kv_items(jp)
                    payload[raw_key] = raw_en
                    changed = True
                else:
                    payload[raw_key] = {}
                    changed = True

            if changed:
                with path.open("w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                migrated += 1
        except Exception:
            failed += 1

    return migrated, failed


def build_public_detail_url(environment: str, code: str, key: str) -> str:
    """Build ARIM Data Portal public detail URL for given environment.
    - production -> nanonet.go.jp
    - test -> CloudFront base with test.nanonet.go.jp path
    Fallback to production pattern if unknown environment.
    """
    base = PROD_BASE if environment == "production" else TEST_BASE if environment == "test" else PROD_BASE
    join = "?mode=detail&code={code}&key={key}"
    return f"{base}{join.format(code=code, key=key)}"


_PUBLIC_FIELD_LABEL_TO_KEY: dict[str, str] = {
    # 基本
    "課題名": "project_title",
    "課題番号": "project_number",
    "データセット登録者": "dataset_registrant",
    "登録者": "dataset_registrant",
    "実施機関": "organization",
    "登録日": "registered_date",
    "エンバーゴ解除日": "embargo_release_date",
    "データセットID": "dataset_id",
    # 解析/可視化
    "ページビュー": "page_views",
    "ダウンロード数": "download_count",
    # 統計
    "データタイル数": "data_tile_count",
    "ファイル数": "file_count",
    "ファイルサイズ": "total_file_size",
    # ライセンス
    "ライセンス": "license",
    # 技術領域
    "重要技術領域（主）": "key_technology_area_primary",
    "重要技術領域（副）": "key_technology_area_secondary",
    "重要技術領域": "key_technology_area",
    "横断技術領域": "crosscutting_technology_area",
    # セクション本文
    "成果発表・成果利用": "outcomes_publications_and_use",
    "マテリアルインデックス": "material_index",
    "キーワードタグ": "keyword_tags",
}


def _normalize_kv_items(raw: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """raw(JP label->value) を (normalized(en_key->value), raw_en(en_key->value)) に変換する。

    - raw_en のキーは "labelの中身の英文表記"（=英語キー）として整理する
    - 未マッピングの項目は raw_en に残さない（必要ならマッピング追加で対応）
    """
    normalized: dict[str, str] = {}
    raw_en: dict[str, str] = {}
    for label, value in raw.items():
        if not value:
            continue
        key = _PUBLIC_FIELD_LABEL_TO_KEY.get(str(label))
        if not key:
            continue
        if key not in raw_en:
            raw_en[key] = str(value)
        if key not in normalized:
            normalized[key] = str(value)
    return normalized, raw_en


@dataclass(frozen=True)
class PublicArimDataLink:
    code: str
    key: str
    url: str
    title: str


@dataclass(frozen=True)
class PublicArimDataDetail:
    code: str
    key: str
    detail_url: str
    title: str
    summary: str
    fields: dict[str, str]
    fields_raw: dict[str, str]
    data_metrics: dict[str, str]
    data_metrics_raw: dict[str, str]
    data_index: dict[str, str]
    data_index_raw: dict[str, str]
    equipment_links: list[dict[str, str]]
    download_links: list[str]
    thumbnails: list[str]


def _get_public_search_url(environment: str) -> str:
    return PROD_BASE if environment == "production" else TEST_BASE if environment == "test" else PROD_BASE


def _get_data_service_root_url(search_url: str) -> str:
    # e.g. https://nanonet.go.jp/data_service/arim_data.php -> https://nanonet.go.jp/data_service/
    # query付きでも動作するようURLとして処理する。
    parsed = urlparse(search_url)
    path = parsed.path
    if path.endswith("/arim_data.php"):
        root_path = path[: -len("arim_data.php")]
    else:
        root_path = path.rsplit("/", 1)[0] + "/"
    return urlunparse(parsed._replace(path=root_path, query="", params="", fragment=""))


def _build_public_headers(origin_url: str, referer_url: str) -> dict:
    # 公開サイトは厳密に必須ではない可能性があるが、ブラウザ再現に寄せる
    parsed = urlparse(origin_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": origin,
        "Referer": referer_url,
    }


def _extract_max_page_from_html(html: str) -> int:
    """ページネーションの最大ページ番号を推定する。

    公開ポータルは `arim_data.php?page=2` のようなリンクでページ移動する。
    """
    pages = [int(m) for m in re.findall(r"[?&]page=(\d+)", html) if m.isdigit()]
    return max(pages) if pages else 1


def _extract_total_count_from_html(html: str) -> Optional[int]:
    """検索結果の総件数をHTMLから推定する。

    例: "1074件中 1～20件" のような表記を想定。
    """
    # よくある表記: "1074件中" / "全1074件"
    m = re.search(r"(\d{1,7})\s*件中", html)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None

    m = re.search(r"全\s*(\d{1,7})\s*件", html)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None

    return None


def _estimate_total_pages_from_html(html: str, *, page_size: int = 20) -> int:
    """ページネーションリンクが無い場合でも、総件数表示からページ数を推定する。"""
    max_page = _extract_max_page_from_html(html)
    total_count = _extract_total_count_from_html(html)
    if total_count and page_size > 0:
        return max(max_page, max(1, math.ceil(total_count / page_size)))
    return max_page


def _build_page_url(search_url: str, page: int) -> str:
    parsed = urlparse(search_url)
    query = parse_qs(parsed.query)
    query["page"] = [str(page)]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def parse_public_arim_data_links(html: str, base_url: str = "https://nanonet.go.jp/data_service/arim_data.php") -> List[PublicArimDataLink]:
    """公開データポータルのHTMLから、詳細ページ（mode=detail）のリンク一覧を抽出。

    base_url は「そのHTMLの元になったページURL」を渡す想定（相対URL解決のため）。
    """
    soup = BeautifulSoup(html, "html.parser")
    links: List[PublicArimDataLink] = []
    seen: set[tuple[str, str]] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "")
        if not isinstance(href, str):
            continue

        if "arim_data.php" not in href or "mode=detail" not in href:
            continue

        # 絶対URLに変換（ページURL基準で解決）
        full_url = urljoin(base_url, href)

        # 一部のページで `/arim_data.php?...` のように /data_service を欠いたURLが混ざるため、
        # base_url が指す arim_data.php のパスへ正規化する。
        try:
            parsed_full = urlparse(full_url)
            parsed_base = urlparse(base_url)
            if (
                parsed_full.scheme == parsed_base.scheme
                and parsed_full.netloc == parsed_base.netloc
                and parsed_full.path.endswith("/arim_data.php")
                and parsed_base.path.endswith("/arim_data.php")
                and parsed_full.path != parsed_base.path
            ):
                full_url = urlunparse(parsed_full._replace(path=parsed_base.path))
        except Exception:
            pass

        # code/key抽出
        try:
            parsed_url = urlparse(full_url)
            params = parse_qs(parsed_url.query)
            code = params.get("code", [""])[0] or ""
            key = params.get("key", [""])[0] or ""
        except Exception:
            continue

        if not code or not key:
            # たまにJSなどで組み立てられるケースに備え、正規表現も試す
            m = re.search(r"[?&]code=([^&]+)", full_url)
            if m:
                code = m.group(1)
            m = re.search(r"[?&]key=([^&]+)", full_url)
            if m:
                key = m.group(1)

        if not code or not key:
            continue

        ck = (code, key)
        if ck in seen:
            continue
        seen.add(ck)

        title = a_tag.get_text(strip=True) or f"ARIM Data {code}"
        links.append(PublicArimDataLink(code=code, key=key, url=full_url, title=title))

    return links


def _extract_dataset_title(soup: BeautifulSoup) -> str:
    # 例: "データセット名：..." を優先
    for tag_name in ("h1", "h2", "h3"):
        for header in soup.find_all(tag_name):
            txt = header.get_text(" ", strip=True)
            if txt.startswith("データセット名"):
                parts = re.split(r"[：:]", txt, maxsplit=1)
                if len(parts) == 2 and parts[1].strip():
                    return parts[1].strip()
    # fallback
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return ""


def _extract_key_value_list(soup: BeautifulSoup, *, section_title: str) -> dict[str, str]:
    # 見出し直下のli/strong形式を収集
    header = soup.find(lambda t: t.name in {"h2", "h3", "h4", "h5"} and t.get_text(strip=True) == section_title)
    if header is None:
        return {}

    out: dict[str, str] = {}
    current = header
    while True:
        current = current.find_next_sibling()
        if current is None:
            break
        if getattr(current, "name", None) in {"h2", "h3", "h4", "h5"}:
            break

        for li in current.find_all("li"):
            strong = li.find("strong")
            if strong is None:
                continue
            label = strong.get_text(" ", strip=True).strip().strip("：:")
            if not label:
                continue
            value = li.get_text(" ", strip=True)
            value = re.sub(rf"^{re.escape(strong.get_text(' ', strip=True))}\s*", "", value).strip()
            value = value.lstrip("：:").strip()
            if value and label not in out:
                out[label] = value

    return out


def _extract_dl_key_values(soup: BeautifulSoup) -> dict[str, str]:
    """<dl><dt>ラベル</dt><dd>値</dd> 形式を抽出する。"""
    out: dict[str, str] = {}
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        for dt in dts:
            dd = dt.find_next_sibling("dd")
            if dd is None:
                continue
            label = dt.get_text(" ", strip=True).strip().strip("：:")
            if not label or label in out:
                continue
            value = dd.get_text(" ", strip=True).strip()
            if value:
                out[label] = value
    return out


def _extract_table_key_values(soup: BeautifulSoup) -> dict[str, str]:
    """<table> 内の key/value を抽出する。

    典型パターン:
    - <tr><th>Label</th><td>Value</td></tr>
    - <tr><td>Label</td><td>Value</td></tr>
    """
    out: dict[str, str] = {}
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True).strip().strip("：:")
            value = cells[1].get_text(" ", strip=True).strip()
            if not label or not value:
                continue
            if label not in out:
                out[label] = value
    return out


def _extract_section_text(soup: BeautifulSoup, *, section_title: str) -> str:
    header = soup.find(lambda t: t.name in {"h2", "h3", "h4", "h5"} and t.get_text(strip=True) == section_title)
    if header is None:
        return ""

    chunks: list[str] = []
    current = header
    while True:
        current = current.find_next_sibling()
        if current is None:
            break
        if getattr(current, "name", None) in {"h2", "h3", "h4", "h5"}:
            break
        txt = current.get_text(" ", strip=True)
        if txt:
            chunks.append(txt)
    return "\n".join(chunks).strip()


def _merge_missing(dst: dict[str, str], src: dict[str, str]) -> None:
    for k, v in src.items():
        if k not in dst and v:
            dst[k] = v


def _extract_summary(soup: BeautifulSoup) -> str:
    header = soup.find(lambda t: t.name in {"h2", "h3", "h4", "h5"} and t.get_text(strip=True) == "要約")
    if header is None:
        return ""

    chunks: list[str] = []
    current = header
    while True:
        current = current.find_next_sibling()
        if current is None:
            break
        if getattr(current, "name", None) in {"h2", "h3", "h4", "h5"}:
            break
        txt = current.get_text(" ", strip=True)
        if txt:
            chunks.append(txt)
    return "\n".join(chunks).strip()


def parse_public_arim_data_detail(html: str, *, page_url: str) -> PublicArimDataDetail:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_dataset_title(soup)

    # ページ全体のli/strongからも拾える分を raw_fields に入れる（網羅的）
    raw_fields: dict[str, str] = {}
    for li in soup.find_all("li"):
        strong = li.find("strong")
        if strong is None:
            continue
        label = strong.get_text(" ", strip=True).strip().strip("：:")
        if not label or label in raw_fields:
            continue
        value = li.get_text(" ", strip=True)
        value = re.sub(rf"^{re.escape(strong.get_text(' ', strip=True))}\s*", "", value).strip()
        value = value.lstrip("：:").strip()
        if value:
            raw_fields[label] = value

    # <dl> と <table> 由来の項目も拾う（ページによってはli/strongが無い）
    _merge_missing(raw_fields, _extract_dl_key_values(soup))
    _merge_missing(raw_fields, _extract_table_key_values(soup))

    raw_data_metrics = _extract_key_value_list(soup, section_title="データメトリックス")
    raw_data_index = _extract_key_value_list(soup, section_title="データインデックス")
    summary = _extract_summary(soup)

    # セクション本文（表形式ではない箇所）も fields に格納
    for sec_title in (
        "成果発表・成果利用",
        "マテリアルインデックス",
        "キーワードタグ",
    ):
        if sec_title not in raw_fields:
            sec_text = _extract_section_text(soup, section_title=sec_title)
            if sec_text:
                raw_fields[sec_title] = sec_text

    fields, fields_raw = _normalize_kv_items(raw_fields)
    data_metrics, data_metrics_raw = _normalize_kv_items(raw_data_metrics)
    data_index, data_index_raw = _normalize_kv_items(raw_data_index)

    # 装置・プロセス
    equipment_links: list[dict[str, str]] = []
    equip_header = soup.find(lambda t: t.name in {"h2", "h3", "h4", "h5"} and t.get_text(strip=True) == "装置・プロセス")
    if equip_header is not None:
        current = equip_header
        while True:
            current = current.find_next_sibling()
            if current is None:
                break
            if getattr(current, "name", None) in {"h2", "h3", "h4", "h5"}:
                break
            for a in current.find_all("a", href=True):
                href = a.get("href")
                if not isinstance(href, str) or not href:
                    continue
                equipment_links.append(
                    {
                        "title": a.get_text(" ", strip=True),
                        "url": urljoin(page_url, href),
                    }
                )

    # ダウンロード/サムネイル
    download_links: list[str] = []
    thumbnails: list[str] = []
    seen_urls: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if not isinstance(href, str) or not href:
            continue
        if "arim_data_file.php" not in href:
            continue
        full = urljoin(page_url, href)
        if full in seen_urls:
            continue
        seen_urls.add(full)

        # freeダウンロードリンクを優先して収集
        if "mode=free" in full:
            download_links.append(full)
        else:
            thumbnails.append(full)

    # code/key は URL から抽出
    parsed_url = urlparse(page_url)
    params = parse_qs(parsed_url.query)
    code = params.get("code", [""])[0] or ""
    key = params.get("key", [""])[0] or ""

    return PublicArimDataDetail(
        code=code,
        key=key,
        detail_url=page_url,
        title=title,
        summary=summary,
        fields=fields,
        fields_raw=fields_raw,
        data_metrics=data_metrics,
        data_metrics_raw=data_metrics_raw,
        data_index=data_index,
        data_index_raw=data_index_raw,
        equipment_links=equipment_links,
        download_links=download_links,
        thumbnails=thumbnails,
    )


def fetch_public_arim_data_detail(
    code: str,
    key: str,
    *,
    environment: str = "production",
    timeout: int = 30,
    headers: Optional[dict] = None,
    basic_auth: Optional[tuple[str, str]] = None,
    cache_enabled: bool = True,
) -> PublicArimDataDetail:
    url = build_public_detail_url(environment, code, key)
    resp = proxy_get(url, headers=headers, timeout=timeout, auth=basic_auth, skip_bearer_token=True)
    resp.encoding = "utf-8"
    return parse_public_arim_data_detail(resp.text, page_url=url)


def fetch_public_arim_data_details(
    links: List[PublicArimDataLink],
    *,
    environment: str = "production",
    timeout: int = 30,
    headers: Optional[dict] = None,
    basic_auth: Optional[tuple[str, str]] = None,
    max_items: Optional[int] = None,
    max_workers: int = 1,
    cache_enabled: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
    item_callback: Optional[DetailItemCallback] = None,
) -> List[PublicArimDataDetail]:
    def _safe_cache_name(code: str, key: str) -> str:
        safe_code = re.sub(r"[^A-Za-z0-9_-]", "_", str(code))
        safe_key = re.sub(r"[^A-Za-z0-9_-]", "_", str(key))
        return f"{safe_code}_{safe_key}.json"

    cache_dir: Path = get_public_data_portal_cache_dir(environment)

    def _load_detail_from_cache(payload: dict, *, fallback_code: str, fallback_key: str) -> PublicArimDataDetail:
        payload_fields = payload.get("fields")
        payload_data_metrics = payload.get("data_metrics")
        payload_data_index = payload.get("data_index")

        raw_fields_payload = payload.get("fields_raw")
        raw_metrics_payload = payload.get("data_metrics_raw")
        raw_index_payload = payload.get("data_index_raw")

        # 新仕様: *_raw は dict で保持
        needs_upgrade = not isinstance(raw_fields_payload, dict)

        if isinstance(raw_fields_payload, dict):
            fields = dict(payload_fields or {})
            fields_raw = dict(raw_fields_payload)
        elif isinstance(raw_fields_payload, list):
            jp = {str(i.get("label")): str(i.get("value")) for i in raw_fields_payload if isinstance(i, dict)}
            fields, fields_raw = _normalize_kv_items(jp)
        else:
            fields, fields_raw = _normalize_kv_items(dict(payload_fields or {}))

        if isinstance(raw_metrics_payload, dict):
            data_metrics = dict(payload_data_metrics or {})
            data_metrics_raw = dict(raw_metrics_payload)
        elif isinstance(raw_metrics_payload, list):
            jp = {str(i.get("label")): str(i.get("value")) for i in raw_metrics_payload if isinstance(i, dict)}
            data_metrics, data_metrics_raw = _normalize_kv_items(jp)
        else:
            data_metrics, data_metrics_raw = _normalize_kv_items(dict(payload_data_metrics or {}))

        if isinstance(raw_index_payload, dict):
            data_index = dict(payload_data_index or {})
            data_index_raw = dict(raw_index_payload)
        elif isinstance(raw_index_payload, list):
            jp = {str(i.get("label")): str(i.get("value")) for i in raw_index_payload if isinstance(i, dict)}
            data_index, data_index_raw = _normalize_kv_items(jp)
        else:
            data_index, data_index_raw = _normalize_kv_items(dict(payload_data_index or {}))

        detail = PublicArimDataDetail(
            code=str(payload.get("code") or fallback_code),
            key=str(payload.get("key") or fallback_key),
            detail_url=str(payload.get("detail_url") or payload.get("url") or ""),
            title=str(payload.get("title") or ""),
            summary=str(payload.get("summary") or ""),
            fields=fields,
            fields_raw=fields_raw,
            data_metrics=data_metrics,
            data_metrics_raw=data_metrics_raw,
            data_index=data_index,
            data_index_raw=data_index_raw,
            equipment_links=list(payload.get("equipment_links") or []),
            download_links=list(payload.get("download_links") or []),
            thumbnails=list(payload.get("thumbnails") or []),
        )
        return detail, needs_upgrade

    def _fetch_one(code: str, key: str) -> PublicArimDataDetail:
        cache_path = cache_dir / _safe_cache_name(code, key)
        if cache_enabled and cache_path.exists():
            try:
                with cache_path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if isinstance(payload, dict):
                    detail, needs_upgrade = _load_detail_from_cache(payload, fallback_code=code, fallback_key=key)
                    if needs_upgrade:
                        try:
                            with cache_path.open("w", encoding="utf-8") as handle:
                                json.dump(detail.__dict__, handle, ensure_ascii=False, indent=2)
                        except OSError:
                            pass
                    return detail
            except Exception:
                pass

        detail = fetch_public_arim_data_detail(
            code,
            key,
            environment=environment,
            timeout=timeout,
            headers=headers,
            basic_auth=basic_auth,
            cache_enabled=True,
        )

        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            with (cache_dir / _safe_cache_name(code, key)).open("w", encoding="utf-8") as handle:
                json.dump(detail.__dict__, handle, ensure_ascii=False, indent=2)
        except OSError:
            pass

        return detail

    selected = list(links)
    if max_items is not None:
        selected = selected[: max(0, max_items)]

    total = len(selected)
    done = 0

    def _emit(message: str) -> None:
        if progress_callback is not None:
            try:
                progress_callback(done, total, message)
            except Exception:
                pass

    _emit("detail取得開始")

    if max_workers <= 1:
        out: list[PublicArimDataDetail] = []
        for link in selected:
            cache_path = cache_dir / _safe_cache_name(link.code, link.key)
            cache_hit = cache_enabled and cache_path.exists()
            detail = _fetch_one(link.code, link.key)
            out.append(detail)
            done += 1
            _emit(f"detail {done}/{total} code={link.code} ({'cache' if cache_hit else 'http'})")
            if item_callback is not None:
                try:
                    item_callback(detail, done, total)
                except Exception:
                    pass
        return out

    results: list[Optional[PublicArimDataDetail]] = [None] * len(selected)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_fetch_one, link.code, link.key): idx for idx, link in enumerate(selected)}
        for future in as_completed(future_map):
            idx = future_map[future]
            detail = future.result()
            results[idx] = detail
            done += 1
            try:
                link = selected[idx]
                cache_path = cache_dir / _safe_cache_name(link.code, link.key)
                cache_hit = cache_enabled and cache_path.exists()
                _emit(f"detail {done}/{total} code={link.code} ({'cache' if cache_hit else 'http'})")
            except Exception:
                _emit(f"detail {done}/{total}")

            if item_callback is not None:
                try:
                    item_callback(detail, done, total)
                except Exception:
                    pass

    return [r for r in results if r is not None]


def search_public_arim_data(
    keyword: str = "",
    *,
    environment: str = "production",
    timeout: int = 30,
    display_result: int = 3,
    display_order: int = 0,
    max_pages: Optional[int] = None,
    start_page: int = 1,
    end_page: Optional[int] = None,
    page_max_workers: int = 1,
    basic_auth: Optional[tuple[str, str]] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> List[PublicArimDataLink]:
    """公開ARIMデータポータルに対して keyword 検索（POST）を行い、詳細リンク一覧を返す。"""
    search_url_base = _get_public_search_url(environment)
    search_url = _with_display_params(search_url_base, display_result=display_result, display_order=display_order)
    data_service_root = _get_data_service_root_url(search_url)
    headers = _build_public_headers(origin_url=search_url, referer_url=data_service_root)

    page_size = _page_size_from_display_result(display_result)
    hard_max_pages = 200

    if start_page < 1:
        start_page = 1
    if end_page is not None and end_page < start_page:
        end_page = start_page

    try:
        if progress_callback is not None:
            try:
                progress_callback(0, 0, "Cookie確立中...")
            except Exception:
                pass

        proxy_get(data_service_root, timeout=timeout, auth=basic_auth, skip_bearer_token=True)

        if progress_callback is not None:
            try:
                progress_callback(0, 0, "検索POST中...")
            except Exception:
                pass

        form_data = {"keyword": keyword or ""}
        resp = proxy_post(
            search_url,
            data=form_data,
            headers=headers,
            timeout=timeout,
            auth=basic_auth,
            skip_bearer_token=True,
        )
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            logger.warning("公開データポータル検索失敗: HTTP %s", resp.status_code)
            return []

        page1_html = resp.text
        links: List[PublicArimDataLink] = []
        seen: set[tuple[str, str]] = set()

        def _extend(new_links: List[PublicArimDataLink]) -> None:
            for link in new_links:
                ck = (link.code, link.key)
                if ck in seen:
                    continue
                seen.add(ck)
                links.append(link)

        if start_page <= 1:
            _extend(parse_public_arim_data_links(page1_html, base_url=search_url))

        detected_max_page = _estimate_total_pages_from_html(page1_html, page_size=page_size)
        effective_max_page = detected_max_page
        if max_pages is not None:
            effective_max_page = min(effective_max_page, max_pages)

        if end_page is not None:
            if detected_max_page <= 1 and end_page > 1:
                effective_max_page = min(end_page, hard_max_pages)
            else:
                effective_max_page = min(effective_max_page, end_page)

        effective_max_page = min(effective_max_page, hard_max_pages)

        loop_start = max(2, start_page)
        pages = list(range(loop_start, effective_max_page + 1))

        def _fetch_page(page: int) -> tuple[int, List[PublicArimDataLink]]:
            page_url = _build_page_url(search_url, page)
            page_resp = proxy_get(
                page_url,
                headers=headers,
                timeout=timeout,
                auth=basic_auth,
                skip_bearer_token=True,
            )
            page_resp.encoding = "utf-8"
            if page_resp.status_code != 200:
                logger.warning("公開データポータルページ取得失敗: page=%s HTTP %s", page, page_resp.status_code)
                return page, []
            return page, parse_public_arim_data_links(page_resp.text, base_url=page_url)

        if pages:
            workers = max(1, int(page_max_workers or 1))
            if workers <= 1 or len(pages) == 1:
                for page in pages:
                    if progress_callback is not None:
                        try:
                            progress_callback(page, effective_max_page, f"検索ページ取得中: page={page}/{effective_max_page}")
                        except Exception:
                            pass
                    _page, page_links = _fetch_page(page)
                    if page_links:
                        _extend(page_links)
            else:
                fetched: dict[int, List[PublicArimDataLink]] = {}
                done = 0
                total = len(pages)
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {executor.submit(_fetch_page, p): p for p in pages}
                    for future in as_completed(futures):
                        page = futures[future]
                        done += 1
                        if progress_callback is not None:
                            try:
                                progress_callback(done, total, f"検索ページ取得中: page={page} ({done}/{total})")
                            except Exception:
                                pass
                        try:
                            page_no, page_links = future.result()
                        except Exception:
                            page_no, page_links = page, []
                        fetched[int(page_no)] = page_links if isinstance(page_links, list) else []

                for page in sorted(fetched.keys()):
                    page_links = fetched.get(page) or []
                    if page_links:
                        _extend(page_links)

        return links

    except Exception as e:
        logger.error("公開データポータル検索エラー: %s", e)
        return []
