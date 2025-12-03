"""
データポータル自動設定ヘルパー

報告書やAIから重要技術領域などの候補を取得する機能を提供
"""

import re
import json
from typing import Dict, Optional, Any, List, Tuple
from bs4 import BeautifulSoup

from classes.managers.log_manager import get_logger
from net.http_helpers import proxy_get
from classes.reports.core.report_scraper import ReportScraper
from classes.ai.core.ai_manager import AIManager
from classes.dataset.util.ai_extension_helper import (
    load_ai_extension_config,
    load_prompt_file,
    format_prompt_with_context,
)
from config.common import OUTPUT_DIR

logger = get_logger("DataPortal.AutoSettingHelper")


# ========= AI提案（設備分類/MI/タグ）ユーティリティ =========

def _load_dataset_basic_context(dataset_id: str) -> Dict[str, Any]:
    """データセットJSONから基本的なコンテキストを抽出

    Returns:
        dict: name, type, description(=existing_description), grant_number
    """
    try:
        from pathlib import Path
        json_dir = Path(OUTPUT_DIR) / "rde" / "data" / "datasets"
        json_file = json_dir / f"{dataset_id}.json"
        if not json_file.exists():
            logger.warning(f"JSONファイルが見つかりません: {json_file}")
            return {}
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 互換: data 直下 or data.data.attributes 形式の両対応
        attributes = (
            data.get("data", {}).get("attributes", {})
            if isinstance(data.get("data"), dict)
            else data.get("attributes", {})
        )
        ctx = {
            "name": attributes.get("name", ""),
            "type": attributes.get("type", ""),
            "existing_description": attributes.get("description", ""),
            "grant_number": attributes.get("grantNumber", ""),
        }
        return ctx
    except Exception as e:
        logger.error(f"基本コンテキスト読込エラー: {e}")
        return {}


def _build_ai_prompt(dataset_id: str, category: str) -> Tuple[Optional[str], Optional[str]]:
    """カテゴリに応じたプロンプトを構築

    Args:
        dataset_id: データセットID
        category: "equipment" | "material_index" | "tag"

    Returns:
        (prompt, output_format) or (None, None) if missing
    """
    conf = load_ai_extension_config()
    dp = conf.get("data_portal_integration", {})
    button_ids = dp.get("suggest_button_ids", {})
    target_id = button_ids.get(category)
    if not target_id:
        logger.warning(f"AIボタンID未設定: category={category}")
        return None, None

    # buttons から該当の設定を取得
    prompt_file = None
    output_format = "text"
    for btn in conf.get("buttons", []):
        if btn.get("id") == target_id:
            prompt_file = btn.get("prompt_file")
            output_format = btn.get("output_format", "text")
            break
    if not prompt_file:
        logger.warning(f"prompt_file未検出: button_id={target_id}")
        return None, None

    raw_template = load_prompt_file(prompt_file)
    if not raw_template:
        logger.warning(f"プロンプトテンプレートが読み込めません: {prompt_file}")
        return None, None

    # DatasetContextCollectorで完全なコンテキストを収集（AI説明文提案と同じフロー）
    from classes.dataset.util.dataset_context_collector import get_dataset_context_collector
    context_collector = get_dataset_context_collector()
    
    # 基本コンテキストを読み込み
    base_ctx = _load_dataset_basic_context(dataset_id)
    
    # collect_full_contextでARIM情報・実験データ・ファイルツリー等を統合
    full_context = context_collector.collect_full_context(
        dataset_id=dataset_id,
        name=base_ctx.get('name', ''),
        type=base_ctx.get('type', ''),
        existing_description=base_ctx.get('existing_description', ''),
        grant_number=base_ctx.get('grant_number', '')
    )
    
    logger.debug(f"完全コンテキスト収集完了: {list(full_context.keys())}")
    
    # format_prompt_with_contextでプレースホルダを置換（ARIM/マスタ/MI統合込み）
    prompt = format_prompt_with_context(raw_template, full_context)
    
    # 未解決プレースホルダの確認
    unresolved = []
    for key in ['file_tree', 'text_from_structured_files', 'arim_extension_data', 'arim_experiment_data', 'experiment_summary', 'dataset_existing_info']:
        if '{' + key + '}' in prompt:
            unresolved.append(key)
    if unresolved:
        logger.warning(f"未解決プレースホルダ（データポータルAI）: {unresolved}")
    
    return prompt, output_format


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # ```json ... ``` のフェンス除去
        try:
            t = t.split("\n", 1)[1]
        except Exception:
            pass
    if t.endswith("```"):
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _try_json_loads(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        return None


def _extract_json_segment(text: str) -> Optional[str]:
    """文字列からJSON（{} もしくは []）の最も大きいセグメントを抽出"""
    # 優先: 配列
    s = text
    lb, rb = s.find("["), s.rfind("]")
    if lb != -1 and rb != -1 and rb > lb:
        return s[lb:rb + 1]
    lb, rb = s.find("{"), s.rfind("}")
    if lb != -1 and rb != -1 and rb > lb:
        return s[lb:rb + 1]
    return None


def _parse_ai_json(text: str) -> Optional[Any]:
    """AI応答テキストからJSONを抽出・パース（簡易サニタイズ対応）"""
    t = _strip_code_fences(text)
    # 全体が引用で包まれている場合（例: '"{...}"' や "'{...}'"）は外側の引用を除去
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    obj = _try_json_loads(t)
    if obj is not None:
        return obj
    seg = _extract_json_segment(t)
    if seg:
        obj = _try_json_loads(seg)
        if obj is not None:
            return obj
    # 軽いトレーリングカンマ対策（行末の , を除去）
    try:
        import re
        t2 = re.sub(r",(\s*[\]\}])", r"\1", t)
        obj = _try_json_loads(t2)
        if obj is not None:
            return obj
    except Exception:
        pass
    return None


def _normalize_proposals(category: str, data: Any) -> List[Dict[str, Any]]:
    """カテゴリ別にAI JSON応答を正規化

    Returns list of {id,label,rank,reason}
    """
    if isinstance(data, list):
        # 既に配列形式（装置/タグの標準）
        return [
            {
                "id": str(item.get("id", "")),
                "label": item.get("label", ""),
                "rank": item.get("rank", None),
                "reason": item.get("reason", ""),
            }
            for item in data if isinstance(item, dict)
        ]

    if isinstance(data, dict):
        # MIは {"dataportal": [...]} または 誤記 {"dataporatal": [...]} を想定
        if category == "material_index":
            arr = None
            for key in ("dataportal", "dataporatal", "dataporTal"):
                if key in data and isinstance(data[key], list):
                    arr = data[key]
                    break
            if arr is not None:
                return _normalize_proposals("material_index", arr)
        # エラーラッパー {error, retries, raw_output} 対応
        raw = data.get("raw_output") if isinstance(data, dict) else None
        if raw:
            inner = _parse_ai_json(raw)
            if inner is not None:
                return _normalize_proposals(category, inner)
    return []


def fetch_ai_proposals_for_category(dataset_id: str, category: str) -> List[Dict[str, Any]]:
    """指定カテゴリのAI提案を同期取得（タイムアウト短縮、JSON正規化）

    Returns proposals: [{id,label,rank,reason}]
    """
    try:
        prompt, output_format = _build_ai_prompt(dataset_id, category)
        if not prompt:
            return []

        ai_manager = AIManager()
        provider = ai_manager.get_default_provider()
        model = ai_manager.get_default_model(provider)

        # タイムアウト短縮（ai_ext_conf の設定を優先）
        conf = load_ai_extension_config()
        timeout_sec = conf.get("data_portal_integration", {}).get("timeout_seconds", 10)
        original_timeout = ai_manager.config.get("timeout")
        ai_manager.config["timeout"] = max(5, int(timeout_sec))

        try:
            result = ai_manager.send_prompt(prompt, provider, model)
        finally:
            # 復元
            if original_timeout is not None:
                ai_manager.config["timeout"] = original_timeout

        if not result.get("success"):
            logger.warning(f"AI応答失敗: {result.get('error')}")
            # 失敗でも raw_output が JSON の場合がある: result にはないためそのまま空返却
            return []

        text = result.get("response") or result.get("content", "")
        data = _parse_ai_json(text)
        if data is None:
            logger.warning("AI応答のJSON解釈に失敗")
            return []
        proposals = _normalize_proposals(category, data)
        # id を文字列化
        for p in proposals:
            p["id"] = str(p.get("id", ""))
        return proposals
    except Exception as e:
        logger.error(f"AI提案取得エラー: {e}")
        return []


def fetch_ai_proposals_for_category_with_debug(dataset_id: str, category: str) -> Tuple[List[Dict[str, Any]], str, str]:
    """AI提案（候補 + 送信プロンプト + 生の受信テキスト）を取得

    Returns: (proposals, prompt_text, raw_response_text)
    """
    proposals: List[Dict[str, Any]] = []
    prompt_text = ""
    raw_text = ""
    try:
        prompt, _ = _build_ai_prompt(dataset_id, category)
        if not prompt:
            return [], "", ""
        prompt_text = prompt

        ai_manager = AIManager()
        provider = ai_manager.get_default_provider()
        model = ai_manager.get_default_model(provider)
        conf = load_ai_extension_config()
        timeout_sec = conf.get("data_portal_integration", {}).get("timeout_seconds", 10)
        original_timeout = ai_manager.config.get("timeout")
        ai_manager.config["timeout"] = max(5, int(timeout_sec))
        try:
            result = ai_manager.send_prompt(prompt, provider, model)
        finally:
            if original_timeout is not None:
                ai_manager.config["timeout"] = original_timeout

        raw_text = result.get("response") or result.get("content", "") or ""
        if not result.get("success"):
            # 失敗でも raw_text がある場合がある
            data = _parse_ai_json(raw_text) if raw_text else None
            if data is not None:
                proposals = _normalize_proposals(category, data)
            return proposals, prompt_text, raw_text

        data = _parse_ai_json(raw_text)
        if data is not None:
            proposals = _normalize_proposals(category, data)
        # 正規化失敗時は空
        for p in proposals:
            p["id"] = str(p.get("id", ""))
        return proposals, prompt_text, raw_text
    except Exception as e:
        logger.error(f"AI提案取得（デバッグ付）エラー: {e}")
        return proposals, prompt_text, raw_text


def extract_important_tech_areas_from_report(dataset_id: str, grant_number: str) -> Dict[str, str]:
    """
    報告書から重要技術領域（主・副）を抽出
    
    Args:
        dataset_id: データセットID
        grant_number: 助成番号（例: JPMXP1222TU0195）
                     課題番号部分（例: 22TU0195）が報告書検索に使用されます
    
    Returns:
        Dict[str, str]: {"main": "主の値", "sub": "副の値"}
                       取得できない場合は空文字列
    """
    logger.info(f"報告書から重要技術領域を抽出: dataset_id={dataset_id}, grant_number={grant_number}")
    
    result = {"main": "", "sub": ""}
    
    try:
        # 助成番号から課題番号を抽出（例: JPMXP1222TU0195 -> 22TU0195）
        # 形式: JPMXP12{課題番号}
        if not grant_number or len(grant_number) < 8:
            logger.warning(f"助成番号が無効です: {grant_number}")
            return result
        
        # JPMXP12を削除して課題番号部分を取得
        task_number = grant_number[7:] if grant_number.startswith("JPMXP12") else grant_number
        logger.info(f"課題番号抽出: {task_number} (元: {grant_number})")
        
        # ReportScraperを使って報告書をキーワード検索
        scraper = ReportScraper()
        
        # POSTキーワード検索で課題番号を直接検索
        report_list = scraper.search_reports_by_keyword(task_number)
        logger.info(f"キーワード検索結果: {len(report_list)}件")
        
        # 検索結果がない場合
        if not report_list:
            logger.warning(f"課題番号 {task_number} に一致する報告書が見つかりませんでした")
            return result
        
        # 最初の報告書を対象とする（通常は1件のみヒット）
        target_report = report_list[0]
        logger.info(f"該当報告書発見: {target_report.get('title', '')} (課題番号: {task_number})")
        
        # 報告書の詳細を取得
        report_url = target_report["url"]
        report_data = scraper.fetch_report(report_url)
        
        if not report_data:
            logger.warning(f"報告書の詳細取得に失敗: {report_url}")
            return result
        
        # 重要技術領域を抽出（report_dataから）
        main_area = report_data.get("重要技術領域・主", "")
        sub_area = report_data.get("重要技術領域・副", "")
        
        result["main"] = main_area
        result["sub"] = sub_area
        
        if main_area or sub_area:
            logger.info(f"重要技術領域抽出成功: main={main_area}, sub={sub_area}")
        else:
            logger.warning(f"報告書に重要技術領域のデータが登録されていません")
        
    except Exception as e:
        logger.error(f"報告書からの重要技術領域抽出エラー: {e}", exc_info=True)
    
    return result


def extract_important_tech_areas_from_report_direct(report_url: str) -> Dict[str, str]:
    """
    報告書URLから直接重要技術領域（主・副）を抽出
    
    Args:
        report_url: 報告書の詳細ページURL
    
    Returns:
        Dict[str, str]: {"main": "主の値", "sub": "副の値"}
                       取得できない場合は空文字列
    """
    logger.info(f"報告書URLから直接重要技術領域を抽出: {report_url}")
    
    result = {"main": "", "sub": ""}
    
    try:
        # HTMLを取得
        response = proxy_get(report_url)
        response.raise_for_status()
        
        # BeautifulSoupでパース
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 技術領域のセクションを検索
        tech_area_tag = soup.find('h5', string='技術領域 / Technology Area')
        
        if tech_area_tag:
            # 横断技術領域の次の<p>が重要技術領域
            cross_tech_element = tech_area_tag.find_next('p')
            
            if cross_tech_element:
                important_tech_element = cross_tech_element.find_next('p')
                
                if important_tech_element:
                    important_tech_text = important_tech_element.text.strip()
                    
                    # 「主: XXX、副: YYY」のようなパターンを解析
                    main_match = re.search(r'主[:：]\s*([^、]+)', important_tech_text)
                    sub_match = re.search(r'副[:：]\s*(.+)', important_tech_text)
                    
                    if main_match:
                        result["main"] = main_match.group(1).strip()
                    if sub_match:
                        result["sub"] = sub_match.group(1).strip()
                    
                    logger.info(f"重要技術領域抽出成功: main={result['main']}, sub={result['sub']}")
        
        if not result["main"] and not result["sub"]:
            logger.warning("重要技術領域の情報が見つかりませんでした")
    
    except Exception as e:
        logger.error(f"報告書URLからの重要技術領域抽出エラー: {e}", exc_info=True)
    
    return result


def get_grant_number_from_dataset_json(dataset_id: str) -> Optional[str]:
    """
    データセットJSONファイルから助成番号(grantNumber)を取得
    
    注: grantNumber形式は JPMXP12{課題番号} (例: JPMXP1222TU0195)
        報告書検索時は課題番号部分(例: 22TU0195)が使用されます
    
    Args:
        dataset_id: データセットID
    
    Returns:
        Optional[str]: 助成番号/grantNumber（取得できない場合はNone）
    """
    try:
        from pathlib import Path
        from config.common import OUTPUT_DIR
        
        # JSONファイルのパスを構築 (データポータル用は datasets ディレクトリ)
        json_dir = Path(OUTPUT_DIR) / "rde" / "data" / "datasets"
        json_file = json_dir / f"{dataset_id}.json"
        
        if not json_file.exists():
            logger.warning(f"JSONファイルが見つかりません: {json_file}")
            return None
        
        # JSONファイルを読み込み
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # data.attributes.grantNumber から助成番号を取得
        grant_number = data.get("data", {}).get("attributes", {}).get("grantNumber", "")
        
        if grant_number:
            logger.info(f"助成番号取得: {grant_number} (dataset_id={dataset_id})")
            return grant_number
        else:
            logger.info(f"助成番号なし (dataset_id={dataset_id}) - データセットに助成番号が設定されていません")
            return None
    
    except Exception as e:
        logger.error(f"助成番号取得エラー: {e}", exc_info=True)
        return None


def suggest_important_tech_areas_with_ai(dataset_id: str) -> Dict[str, str]:
    """
    AIで重要技術領域（主・副）を推定
    
    Args:
        dataset_id: データセットID
    
    Returns:
        Dict[str, str]: {"main": "主の値", "sub": "副の値"}
                       取得できない場合は空文字列
    """
    logger.info(f"AIで重要技術領域を推定: dataset_id={dataset_id}")
    
    result = {"main": "", "sub": ""}
    
    try:
        from pathlib import Path
        from config.common import OUTPUT_DIR
        
        # JSONファイルを読み込んでコンテキスト情報を取得 (データポータル用は datasets ディレクトリ)
        json_dir = Path(OUTPUT_DIR) / "rde" / "data" / "datasets"
        json_file = json_dir / f"{dataset_id}.json"
        
        if not json_file.exists():
            logger.warning(f"JSONファイルが見つかりません: {json_file}")
            return result
        
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # データセット情報を抽出
        attributes = data.get("attributes", {})
        dataset_name = attributes.get("name", "")
        dataset_description = attributes.get("description", "")
        grant_number = attributes.get("grantNumber", "")
        
        # AI設定を取得
        from classes.config.ui.ai_settings_widget import get_ai_config
        ai_config = get_ai_config()
        provider = ai_config.get('default_provider', 'gemini') if ai_config else 'gemini'
        model = ai_config.get('providers', {}).get(provider, {}).get('default_model', 'gemini-2.0-flash') if ai_config else 'gemini-2.0-flash'
        
        # プロンプトを作成
        prompt = f"""以下のデータセット情報から、ARIM（先端研究基盤共用促進事業）の重要技術領域（主・副）を推定してください。

データセット情報:
- 名前: {dataset_name}
- 説明: {dataset_description}
- 助成番号: {grant_number}

重要技術領域は以下のカテゴリから選択してください:
1. ナノテクノロジー・材料
2. エネルギー
3. ライフサイエンス
4. 環境
5. ものづくり技術（加工・計測・制御）
6. 情報通信
7. 社会インフラ
8. その他

回答形式:
主: [カテゴリ名]
副: [カテゴリ名（該当する場合のみ）]

※簡潔に回答してください。説明は不要です。"""
        
        # AIリクエストを実行
        ai_manager = AIManager()
        logger.info(f"AIリクエスト開始: provider={provider}, model={model}")
        ai_result = ai_manager.send_prompt(prompt, provider, model)
        
        if ai_result.get('success', False):
            response_text = ai_result.get('response') or ai_result.get('content', '')
            logger.info(f"AIリクエスト成功: {len(response_text)}文字の応答")
            # JSON応答（dataportal/MItree）優先で解析し、失敗時はテキスト正規表現にフォールバック
            parsed_json = None
            try:
                parsed_json = json.loads(response_text)
            except Exception:
                parsed_json = None

            if isinstance(parsed_json, dict):
                dp_key = 'dataportal' if 'dataportal' in parsed_json else ('dataporatal' if 'dataporatal' in parsed_json else None)
                mi_list = parsed_json.get('MItree') or []
                if mi_list and isinstance(mi_list, list):
                    # 参考情報として返す（AutoSettingDialogで併記）
                    try:
                        # 正規化: 各要素を {rank,label,reason} の辞書に
                        ref_items = []
                        for item in mi_list:
                            ref_items.append({
                                'rank': item.get('rank'),
                                'label': item.get('label'),
                                'reason': item.get('reason'),
                                'hierarchy': item.get('hierarchy')
                            })
                        result['MItree'] = ref_items
                    except Exception:
                        result['MItree'] = mi_list  # 元のまま
                if dp_key and isinstance(parsed_json.get(dp_key), list) and parsed_json.get(dp_key):
                    top = parsed_json.get(dp_key)[0]
                    label = top.get('label') if isinstance(top, dict) else str(top)
                    result['main'] = label or result['main']
                    # 副候補が存在すれば2番目を使用
                    if len(parsed_json.get(dp_key)) > 1:
                        second = parsed_json.get(dp_key)[1]
                        result['sub'] = (second.get('label') if isinstance(second, dict) else str(second)) or result['sub']
                else:
                    # テキスト形式フォールバック
                    main_match = re.search(r'主[:：]\s*(.+?)(?:\n|$)', response_text)
                    sub_match = re.search(r'副[:：]\s*(.+?)(?:\n|$)', response_text)
                    if main_match:
                        result["main"] = main_match.group(1).strip()
                    if sub_match:
                        result["sub"] = sub_match.group(1).strip()
            else:
                # テキスト形式のみ
                main_match = re.search(r'主[:：]\s*(.+?)(?:\n|$)', response_text)
                sub_match = re.search(r'副[:：]\s*(.+?)(?:\n|$)', response_text)
                if main_match:
                    result["main"] = main_match.group(1).strip()
                if sub_match:
                    result["sub"] = sub_match.group(1).strip()
            
            logger.info(f"AI推定成功: main={result['main']}, sub={result['sub']}")
        else:
            error_msg = ai_result.get('error', '不明なエラー')
            logger.error(f"AIリクエスト失敗: {error_msg}")
    
    except Exception as e:
        logger.error(f"AIでの重要技術領域推定エラー: {e}", exc_info=True)
    
    return result


def extract_cross_tech_areas_from_report(dataset_id: str, grant_number: str) -> Dict[str, str]:
    """
    報告書から横断技術領域（主・副）を抽出
    
    Args:
        dataset_id: データセットID
        grant_number: 助成番号（例: JPMXP1222TU0195）
    
    Returns:
        Dict[str, str]: {"main": "主の値", "sub": "副の値"}
    """
    logger.info(f"報告書から横断技術領域を抽出: dataset_id={dataset_id}, grant_number={grant_number}")
    
    result = {"main": "", "sub": ""}
    
    try:
        # 課題番号を抽出
        if not grant_number or len(grant_number) < 8:
            logger.warning(f"助成番号が無効です: {grant_number}")
            return result
        
        task_number = grant_number[7:] if grant_number.startswith("JPMXP12") else grant_number
        logger.info(f"課題番号抽出: {task_number} (元: {grant_number})")
        
        # 報告書を検索
        scraper = ReportScraper()
        report_list = scraper.search_reports_by_keyword(task_number)
        
        if not report_list:
            logger.warning(f"課題番号 {task_number} に一致する報告書が見つかりませんでした")
            return result
        
        target_report = report_list[0]
        logger.info(f"該当報告書発見: {target_report.get('title', '')} (課題番号: {task_number})")
        
        # 報告書詳細を取得
        report_data = scraper.fetch_report(target_report["url"])
        
        if not report_data:
            logger.warning(f"報告書の詳細取得に失敗")
            return result
        
        # 横断技術領域を抽出
        main_area = report_data.get("横断技術領域・主", "")
        sub_area = report_data.get("横断技術領域・副", "")
        
        result["main"] = main_area
        result["sub"] = sub_area
        
        if main_area or sub_area:
            logger.info(f"横断技術領域抽出成功: main={main_area}, sub={sub_area}")
        else:
            logger.warning(f"報告書に横断技術領域のデータが登録されていません")
        
    except Exception as e:
        logger.error(f"報告書からの横断技術領域抽出エラー: {e}", exc_info=True)
    
    return result


def extract_equipment_from_report(dataset_id: str, grant_number: str) -> Dict[str, any]:
    """
    報告書から利用した主な設備を抽出
    
    Args:
        dataset_id: データセットID
        grant_number: 助成番号（例: JPMXP1222TU0195）
    
    Returns:
        Dict: {"equipment": [設備リスト], "text": "設備名（改行区切り）"}
    """
    logger.info(f"報告書から設備情報を抽出: dataset_id={dataset_id}, grant_number={grant_number}")
    
    result = {"equipment": [], "text": ""}
    
    try:
        # 課題番号を抽出
        if not grant_number or len(grant_number) < 8:
            logger.warning(f"助成番号が無効です: {grant_number}")
            return result
        
        task_number = grant_number[7:] if grant_number.startswith("JPMXP12") else grant_number
        logger.info(f"課題番号抽出: {task_number} (元: {grant_number})")
        
        # 報告書を検索
        scraper = ReportScraper()
        report_list = scraper.search_reports_by_keyword(task_number)
        
        if not report_list:
            logger.warning(f"課題番号 {task_number} に一致する報告書が見つかりませんでした")
            return result
        
        target_report = report_list[0]
        logger.info(f"該当報告書発見: {target_report.get('title', '')} (課題番号: {task_number})")
        
        # 報告書詳細を取得
        report_data = scraper.fetch_report(target_report["url"])
        
        if not report_data:
            logger.warning(f"報告書の詳細取得に失敗")
            return result
        
        # 利用した主な設備を抽出（リスト形式）
        equipment_list = report_data.get("利用した主な設備 / Equipment Used in This Project", [])
        
        if isinstance(equipment_list, list) and equipment_list:
            result["equipment"] = equipment_list
            # テキスト形式（改行区切り）
            result["text"] = "\n".join(equipment_list)
            logger.info(f"設備情報抽出成功: {len(equipment_list)}件")
        else:
            logger.warning(f"報告書に設備情報が登録されていません")
        
    except Exception as e:
        logger.error(f"報告書からの設備情報抽出エラー: {e}", exc_info=True)
    
    return result


def extract_publications_from_report(dataset_id: str, grant_number: str) -> Dict[str, any]:
    """
    報告書から論文・プロシーディング（DOI）を抽出
    
    Args:
        dataset_id: データセットID
        grant_number: 助成番号（例: JPMXP1222TU0195）
    
    Returns:
        Dict: {"publications": [論文リスト], "text": "論文情報（改行区切り）"}
    """
    logger.info(f"報告書から論文情報を抽出: dataset_id={dataset_id}, grant_number={grant_number}")
    
    result = {"publications": [], "text": ""}
    
    try:
        # 課題番号を抽出
        if not grant_number or len(grant_number) < 8:
            logger.warning(f"助成番号が無効です: {grant_number}")
            return result
        
        task_number = grant_number[7:] if grant_number.startswith("JPMXP12") else grant_number
        logger.info(f"課題番号抽出: {task_number} (元: {grant_number})")
        
        # 報告書を検索
        scraper = ReportScraper()
        report_list = scraper.search_reports_by_keyword(task_number)
        
        if not report_list:
            logger.warning(f"課題番号 {task_number} に一致する報告書が見つかりませんでした")
            return result
        
        target_report = report_list[0]
        logger.info(f"該当報告書発見: {target_report.get('title', '')} (課題番号: {task_number})")
        
        # 報告書詳細を取得
        report_data = scraper.fetch_report(target_report["url"])
        
        if not report_data:
            logger.warning(f"報告書の詳細取得に失敗")
            return result
        
        # 論文・プロシーディング（DOI）を抽出（リスト形式）
        publications_list = report_data.get("論文・プロシーディング（DOIのあるもの） / DOI (Publication and Proceedings)", [])
        
        if isinstance(publications_list, list) and publications_list:
            result["publications"] = publications_list
            # テキスト形式（改行区切り）
            result["text"] = "\n".join(publications_list)
            logger.info(f"論文情報抽出成功: {len(publications_list)}件")
        else:
            logger.warning(f"報告書に論文情報が登録されていません")
        
    except Exception as e:
        logger.error(f"報告書からの論文情報抽出エラー: {e}", exc_info=True)
    
    return result
