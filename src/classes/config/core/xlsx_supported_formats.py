from __future__ import annotations

import re
from typing import List, Dict, Optional

import pandas as pd

from .models import SupportedFileFormatEntry


# 版表記のゆれに対応（例: 【V3版】, 【V 3 版】, V3版, v3版, V3, 【V3】等）
VERSION_RE = re.compile(r"[【(\[]?\s*[Vv]\s*(\d+)(?:\s*版)?\s*[】)\]]?")


def _normalize_ext(raw: str) -> str:
    """拡張子を正規化（.txt → txt, .JPEG → jpg 等）"""
    s = raw.strip().lower()
    s = s.replace("．", ".")  # 全角ドット
    # 先頭のドット除去
    s = s.lstrip('.')
    # 空白や記号除去
    s = re.sub(r"[^a-z0-9]", "", s)
    # 名称マップ
    name_map = {
        "tiff": "tif", "tif": "tif",
        "jpeg": "jpg", "jpe": "jpg", "jpg": "jpg",
        "png": "png", "csv": "csv", "json": "json",
        "excel": "xlsx", "xls": "xls", "xlsx": "xlsx",
        "txt": "txt", "pdf": "pdf", "xml": "xml",
    }
    return name_map.get(s, s)


def _extract_exts_with_desc(text: str) -> Dict[str, str]:
    """複合記述から {拡張子: 説明} 辞書を抽出。
    例: ".rawファイル（スペクトル）\n.xlsxファイル（測定条件）" 
        → {'raw': 'スペクトル', 'xlsx': '測定条件'}
    """
    if not isinstance(text, str):
        return {}
    # 改行や全角スペースを統一
    t = text.replace('\n', ' ').replace('\r', ' ').replace('　', ' ')
    t = re.sub(r"\s+", " ", t)
    
    # パターン: .ext + オプション「ファイル」 + 括弧内説明
    # 例: .raw, .rawファイル, .rawファイル（説明）, .raw（説明）
    pattern = r"\.([a-z0-9]+)(?:ファイル)?(?:[（(]([^）)]+)[）)])?"
    matches = re.finditer(pattern, t, flags=re.IGNORECASE)
    
    result = {}
    for m in matches:
        ext_raw = m.group(1)
        desc = m.group(2) if m.group(2) else ""
        ext_norm = _normalize_ext(ext_raw)
        if ext_norm:
            # 既存があれば追記
            if ext_norm in result and desc:
                result[ext_norm] = result[ext_norm] + "," + desc.strip()
            else:
                result[ext_norm] = desc.strip()
    
    return result


def _extract_version(s: str) -> Optional[int]:
    if not isinstance(s, str):
        return None
    m = VERSION_RE.search(s)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def parse_supported_formats(xlsx_path: str) -> List[SupportedFileFormatEntry]:
    """複数シートXLSXを解析し、対応ファイル形式の一覧を抽出する。

    期待列（ゆらぎあり）:
      - equipment_id: ["装置ID", "機器ID", "equipment_id"]
      - file_format: ["登録ファイル形式", "ファイル形式", "file_format"]
      - template_name: ["テンプレート名", "データセットテンプレート名", "template_name"]
      - template_version_label: ["テンプレート版", "テンプレート（【V?版】）", "template_version"]
      - dataset_id: ["データセットID", "dataset_id"] (任意)
    """

    # 全シート読み込み
    xl = pd.ExcelFile(xlsx_path)
    entries: List[SupportedFileFormatEntry] = []

    col_map_candidates: Dict[str, List[str]] = {
        "equipment_id": ["装置ID", "機器ID", "equipment_id"],
        "file_format": ["登録ファイル形式", "ファイル形式", "file_format"],
        "template_name": ["テンプレート名", "データセットテンプレート名", "template_name"],
        # 全角/半角括弧・文字揺らぎの両対応
        "template_version_label": [
            "テンプレート版",
            "テンプレート（【V?版】）",  # 全角閉じ括弧
            "テンプレート（【V?版】)",   # 半角閉じ括弧
            "template_version",
        ],
        "dataset_id": ["データセットID", "dataset_id"],
    }

    def resolve(df: pd.DataFrame, key: str) -> Optional[str]:
        # 1) 完全一致
        for candidate in col_map_candidates[key]:
            if candidate in df.columns:
                return candidate
        # 2) 部分一致（日本語ゆれ・括弧除去）
        norm = lambda s: re.sub(r"[（）()【】]", "", s)
        candidates = [norm(c) for c in col_map_candidates[key]]
        for col in df.columns:
            cnorm = norm(str(col))
            for cand in candidates:
                if cand and cand in cnorm:
                    return col
        return None

    def reheader_if_needed(df: pd.DataFrame) -> pd.DataFrame:
        """ヘッダが1行目でない場合に、候補見出しの存在する行をヘッダとして再設定"""
        cols = set(sum(col_map_candidates.values(), []))
        # 行毎に一致スコアを計算
        best_idx = None
        best_score = 0
        for idx in range(min(10, len(df))):  # 先頭〜10行まで探査
            row_vals = [str(v).strip() for v in df.iloc[idx].tolist()]
            score = sum(1 for v in row_vals if v in cols)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is not None and best_score >= 2:
            # この行をヘッダにして以降をデータにする
            header = [str(v).strip() for v in df.iloc[best_idx].tolist()]
            new_df = df.iloc[best_idx + 1:].copy()
            # 列数差は短い方に合わせる
            n = min(len(header), new_df.shape[1])
            new_df = new_df.iloc[:, :n]
            new_df.columns = header[:n]
            return new_df
        return df

    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name)
        df = reheader_if_needed(df)
        # 列解決
        equipment_col = resolve(df, "equipment_id")
        file_col = resolve(df, "file_format")
        tmpl_col = resolve(df, "template_name")
        ver_col = resolve(df, "template_version_label")
        dataset_col = resolve(df, "dataset_id")

        # 必須列がなければスキップ
        if not (equipment_col and file_col and tmpl_col):
            continue

        for _, row in df.iterrows():
            equipment_id = str(row[equipment_col]).strip() if pd.notna(row.get(equipment_col)) else ""
            file_fmt_raw = str(row[file_col]).strip() if pd.notna(row.get(file_col)) else ""
            template_name = str(row[tmpl_col]).strip() if pd.notna(row.get(tmpl_col)) else ""
            version_label = str(row[ver_col]).strip() if (ver_col and pd.notna(row.get(ver_col))) else ""
            dataset_id = str(row[dataset_col]).strip() if (dataset_col and pd.notna(row.get(dataset_col))) else None

            if not equipment_id or not file_fmt_raw or not template_name:
                continue

            template_version = _extract_version(version_label)
            ext_desc_map = _extract_exts_with_desc(file_fmt_raw)
            if not ext_desc_map:
                # フォールバック
                ext_desc_map = {_normalize_ext(file_fmt_raw): ""}
            
            exts_list = sorted(ext_desc_map.keys())
            
            entries.append(
                SupportedFileFormatEntry(
                    equipment_id=equipment_id,
                    file_exts=exts_list,
                    file_descs=ext_desc_map,
                    template_name=template_name,
                    template_version=template_version,
                    source_sheet=sheet_name,
                    original_format=file_fmt_raw,
                )
            )

    # 同一(equipment_id, template_name)で最新版に集約
    latest: Dict[tuple, SupportedFileFormatEntry] = {}
    for e in entries:
        key = (e.equipment_id, e.template_name)
        cur = latest.get(key)
        if cur is None:
            latest[key] = e
        else:
            # Noneより数値を優先、数値同士なら大きい方
            def ver(v: Optional[int]) -> int:
                return -1 if v is None else v
            if ver(e.template_version) >= ver(cur.template_version):
                latest[key] = e

    return list(latest.values())
