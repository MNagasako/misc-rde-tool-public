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
    
    対応パターン:
    - 基本: .rawファイル（スペクトル）
    - スラッシュ区切り: .dm3/4ファイル → dm3, dm4
    - カンマ区切り: .dm3, .dm4ファイル → dm3, dm4
    - 全角カンマ区切り: .dm3、.dm4ファイル → dm3, dm4
    - 改行区切り: .tif\n.tiff → tif, tiff
    - 「または」区切り: .txt または .csv → txt, csv
    - 「or」区切り: .txt or .dx → txt, dx
    - ドットなしスラッシュ: .jdf/.jdx → jdf, jdx
    
    例: ".rawファイル（スペクトル）\n.xlsxファイル（測定条件）" 
        → {'raw': 'スペクトル', 'xlsx': '測定条件'}
    例: ".dm3/4ファイル（スペクトル/測定条件）"
        → {'dm3': 'スペクトル/測定条件', 'dm4': 'スペクトル/測定条件'}
    """
    if not isinstance(text, str):
        return {}
    
    # === 前処理: 全角文字を半角に正規化 ===
    # 全角記号を半角に統一
    t = text
    t = t.replace('．', '.')  # 全角ドット
    t = t.replace('、', ',')  # 全角カンマ
    t = t.replace('，', ',')  # 全角カンマ（別形式）
    t = t.replace('（', '(')  # 全角括弧
    t = t.replace('）', ')')  
    t = t.replace('【', '[')
    t = t.replace('】', ']')
    t = t.replace('　', ' ')  # 全角スペース
    
    # 改行を空白に統一
    t = t.replace('\n', ' ').replace('\r', ' ')
    
    # 連続する空白を1つに圧縮
    t = re.sub(r"\s+", " ", t)
    
    result = {}
    
    # === パターン1: 複合拡張子（スラッシュ区切り）の展開 ===
    # 例: .dm3/4 → .dm3, .dm4
    # 例: .tif/tiff → .tif, .tiff
    # パターン: .拡張子1/拡張子2 または .拡張子1/数字
    def expand_slash_notation(m: re.Match) -> str:
        """スラッシュ記法を展開: .dm3/4 → .dm3, .dm4"""
        prefix = m.group(1)  # 先頭の拡張子部分
        suffix = m.group(2)  # スラッシュ後の部分
        
        # 数字のみの場合（例: dm3/4）
        if suffix.isdigit():
            # 先頭から数字以外を削除して基本部分を取得
            base = re.sub(r'\d+$', '', prefix)
            # 展開: dm3, dm4
            expanded = f".{prefix}, .{base}{suffix}"
            return expanded
        else:
            # 文字列の場合（例: tif/tiff）
            expanded = f".{prefix}, .{suffix}"
            return expanded
    
    # スラッシュ区切りを展開（後続の「ファイル」や括弧は保持）
    t = re.sub(r'\.([a-z0-9]+)/([a-z0-9]+)', expand_slash_notation, t, flags=re.IGNORECASE)
    
    # === パターン2: 「または」「or」を半角カンマに統一 ===
    t = re.sub(r'\s*または\s*', ', ', t)
    t = re.sub(r'\s+or\s+', ', ', t, flags=re.IGNORECASE)
    
    # === パターン3: 複数拡張子の抽出 ===
    # マッチパターン: .ext または ext のみ（カンマ・スペース区切り対応）
    # 全体を複数の拡張子候補として分割抽出
    
    # 括弧内の説明文を一時的に保護（先に抽出）
    desc_pattern = r'[([（]([^)\]）]+)[)\]）]'
    descriptions = []
    def save_desc(m: re.Match) -> str:
        idx = len(descriptions)
        descriptions.append(m.group(1).strip())
        return f"__DESC{idx}__"
    
    t_protected = re.sub(desc_pattern, save_desc, t)
    
    # 拡張子パターン抽出: .ext または ext（「ファイル」「file」等のキーワードも除外）
    # カンマやスペースで区切られた拡張子を全て抽出
    ext_pattern = r'\.?([a-z0-9]+)(?:ファイル|file)?'
    
    # 抽出候補をリスト化
    ext_candidates = []
    for token in re.split(r'[,\s]+', t_protected):
        token = token.strip()
        if not token or token.startswith('__DESC'):
            continue
        # ドットで始まるまたは英数字のみのトークン
        m = re.match(r'^\.?([a-z0-9]+)(?:ファイル|file)?$', token, re.IGNORECASE)
        if m:
            ext_raw = m.group(1)
            # 明らかに拡張子でない文字列をフィルタ（日本語・長すぎる等）
            if len(ext_raw) <= 10 and re.match(r'^[a-z0-9]+$', ext_raw, re.IGNORECASE):
                ext_candidates.append(ext_raw)
    
    # === パターン4: 正規表現による詳細マッチング（フォールバック） ===
    # より複雑なパターンに対応（「.ext(説明)」形式）
    detailed_pattern = r'\.([a-z0-9]+)(?:ファイル|file)?(?:[([（]([^)\]）]+)[)\]）])?'
    for m in re.finditer(detailed_pattern, t, flags=re.IGNORECASE):
        ext_raw = m.group(1)
        desc = m.group(2).strip() if m.group(2) else ""
        
        if len(ext_raw) <= 10 and re.match(r'^[a-z0-9]+$', ext_raw, re.IGNORECASE):
            ext_norm = _normalize_ext(ext_raw)
            if ext_norm:
                # 説明文の保護されたプレースホルダーを復元
                for idx, saved_desc in enumerate(descriptions):
                    desc = desc.replace(f"__DESC{idx}__", saved_desc)
                
                if ext_norm in result:
                    # 既存の説明がある場合は追記
                    if desc and desc not in result[ext_norm]:
                        result[ext_norm] = result[ext_norm] + "/" + desc
                else:
                    result[ext_norm] = desc
    
    # === パターン5: シンプルな拡張子候補の追加 ===
    # 上記パターンで拾えなかった候補を追加
    for ext_raw in ext_candidates:
        ext_norm = _normalize_ext(ext_raw)
        if ext_norm and ext_norm not in result:
            result[ext_norm] = ""
    
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
