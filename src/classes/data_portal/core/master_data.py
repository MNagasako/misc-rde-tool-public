"""
マスタデータ管理モジュール

ARIMデータポータルサイトからマテリアルインデックスとタグのマスタデータを取得・保存・管理
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from datetime import datetime

from bs4 import BeautifulSoup

from classes.managers.log_manager import get_logger
from config.common import get_dynamic_file_path

logger = get_logger("DataPortal.MasterData")


class MasterDataManager:
    """
    マスタデータ管理クラス
    
    機能:
    - マテリアルインデックスとタグのマスタデータ取得
    - HTMLテーブルからのデータ抽出
    - マスタデータの保存・読み込み
    - 環境別（test/production）管理
    """
    
    # マスタデータ保存先ディレクトリ
    MASTER_DATA_DIR = "input/master_data"
    
    # マスタデータファイル名パターン
    MATERIAL_INDEX_FILE = "material_index_{env}.json"
    TAG_FILE = "tag_{env}.json"
    EQUIPMENT_FILE = "equipment_{env}.json"  # 設備分類
    
    def __init__(self, portal_client):
        """
        初期化
        
        Args:
            portal_client: PortalClientインスタンス
        """
        self.client = portal_client
        self.environment = portal_client.environment
        
        # マスタデータディレクトリを作成
        self.master_data_dir = Path(get_dynamic_file_path(self.MASTER_DATA_DIR))
        self.master_data_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"MasterDataManager 初期化: {self.environment} 環境")
    
    def fetch_material_index_master(self) -> Tuple[bool, Dict[str, str]]:
        """
        マテリアルインデックスマスタを取得（全ページ対応）
        
        Returns:
            Tuple[bool, Dict[str, str]]: (成功フラグ, {コード: 名称} の辞書)
        """
        logger.info("マテリアルインデックスマスタ取得開始...")
        
        try:
            material_index_map = {}
            page = 1
            
            while True:
                logger.info(f"ページ {page} を取得中...")
                
                # POSTリクエスト送信
                success, response = self.client.post(
                    "main.php",
                    data={
                        "mode": "master_material_index",
                        "page": str(page)
                    }
                )
                
                if not success:
                    logger.error(f"マテリアルインデックスマスタ取得失敗: {response}")
                    return False, {}
                
                # HTMLをパース
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # テーブルを探す
                tables = soup.find_all('table')
                
                if not tables:
                    logger.error("マテリアルインデックスマスタ: テーブルが見つかりません")
                    # デバッグ用にHTMLを保存
                    self._save_debug_html(f"material_index_page{page}", response.text)
                    break
                
                # テーブルからデータを抽出
                table = tables[0]
                rows = table.find_all('tr')
                
                page_data_count = 0
                
                # 各行を処理
                for row in rows:
                    # hidden inputからコードを取得
                    mmi_code_input = row.find('input', {'name': 'mmi_code'})
                    if not mmi_code_input:
                        continue
                    
                    code = mmi_code_input.get('value', '').strip()
                    
                    # class='l'のtdから名称を取得
                    name_td = row.find('td', {'class': 'l'})
                    if not name_td:
                        continue
                    
                    name = name_td.get_text(strip=True)
                    
                    if code and name:
                        material_index_map[code] = name
                        page_data_count += 1
                
                logger.info(f"ページ {page}: {page_data_count} 件取得")
                
                # 次のページがあるかチェック
                # ページネーションリンクを探す（複数パターン対応）
                # パターン1: "次へ"テキストを含むリンク
                next_page_link = soup.find('a', text=lambda t: t and '次へ' in t)
                
                # パターン2: "次へ"を含む要素内のリンク
                if not next_page_link:
                    for link in soup.find_all('a'):
                        link_text = link.get_text(strip=True)
                        if '次' in link_text or 'Next' in link_text or '>' in link_text:
                            # hrefがあり、pageパラメータを含むリンク
                            href = link.get('href', '')
                            if 'page=' in href or link.get('onclick'):
                                next_page_link = link
                                logger.info(f"次ページリンク検出: {link_text}, href={href}")
                                break
                
                # パターン3: データが100件の場合は次ページがあると仮定
                has_next_page = False
                if next_page_link:
                    logger.info(f"次ページリンク発見: ページ{page+1}へ")
                    has_next_page = True
                elif page_data_count >= 100:
                    logger.info(f"データ件数が100件のため次ページを試行: ページ{page+1}へ")
                    has_next_page = True
                
                if not has_next_page or page_data_count == 0:
                    logger.info(f"ページネーション終了: 最終ページ={page}")
                    break
                
                page += 1
            
            logger.info(f"マテリアルインデックスマスタ取得成功: 合計 {len(material_index_map)} 件")
            
            return True, material_index_map
            
        except Exception as e:
            logger.error(f"マテリアルインデックスマスタ取得エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, {}
    
    def fetch_tag_master(self) -> Tuple[bool, Dict[str, str]]:
        """
        タグマスタを取得（全ページ対応）
        
        Returns:
            Tuple[bool, Dict[str, str]]: (成功フラグ, {コード: 名称} の辞書)
        """
        logger.info("タグマスタ取得開始...")
        
        try:
            tag_map = {}
            page = 1
            
            while True:
                logger.info(f"ページ {page} を取得中...")
                
                # POSTリクエスト送信
                success, response = self.client.post(
                    "main.php",
                    data={
                        "mode": "master_tag",
                        "page": str(page)
                    }
                )
                
                if not success:
                    logger.error(f"タグマスタ取得失敗: {response}")
                    return False, {}
                
                # HTMLをパース
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # テーブルを探す
                tables = soup.find_all('table')
                
                if not tables:
                    logger.error("タグマスタ: テーブルが見つかりません")
                    # デバッグ用にHTMLを保存
                    self._save_debug_html(f"tag_page{page}", response.text)
                    break
                
                # テーブルからデータを抽出
                table = tables[0]
                rows = table.find_all('tr')
                
                page_data_count = 0
                
                # 各行を処理
                for row in rows:
                    # hidden inputからコードを取得
                    mt_code_input = row.find('input', {'name': 'mt_code'})
                    if not mt_code_input:
                        continue
                    
                    code = mt_code_input.get('value', '').strip()
                    
                    # class='l'のtdから名称を取得
                    name_td = row.find('td', {'class': 'l'})
                    if not name_td:
                        continue
                    
                    name = name_td.get_text(strip=True)
                    
                    if code and name:
                        tag_map[code] = name
                        page_data_count += 1
                
                logger.info(f"ページ {page}: {page_data_count} 件取得")
                
                # 次のページがあるかチェック
                # ページネーションリンクを探す（複数パターン対応）
                # パターン1: "次へ"テキストを含むリンク
                next_page_link = soup.find('a', text=lambda t: t and '次へ' in t)
                
                # パターン2: "次へ"を含む要素内のリンク
                if not next_page_link:
                    for link in soup.find_all('a'):
                        link_text = link.get_text(strip=True)
                        if '次' in link_text or 'Next' in link_text or '>' in link_text:
                            # hrefがあり、pageパラメータを含むリンク
                            href = link.get('href', '')
                            if 'page=' in href or link.get('onclick'):
                                next_page_link = link
                                logger.info(f"次ページリンク検出: {link_text}, href={href}")
                                break
                
                # パターン3: データが100件の場合は次ページがあると仮定
                has_next_page = False
                if next_page_link:
                    logger.info(f"次ページリンク発見: ページ{page+1}へ")
                    has_next_page = True
                elif page_data_count >= 100:
                    logger.info(f"データ件数が100件のため次ページを試行: ページ{page+1}へ")
                    has_next_page = True
                
                if not has_next_page or page_data_count == 0:
                    logger.info(f"ページネーション終了: 最終ページ={page}")
                    break
                
                page += 1
            
            logger.info(f"タグマスタ取得成功: 合計 {len(tag_map)} 件")
            
            return True, tag_map
            
        except Exception as e:
            logger.error(f"タグマスタ取得エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, {}
    
    def save_material_index_master(self, data: Dict[str, str]) -> bool:
        """
        マテリアルインデックスマスタを保存
        
        Args:
            data: {コード: 名称} の辞書
        
        Returns:
            bool: 成功フラグ
        """
        try:
            filepath = self.master_data_dir / self.MATERIAL_INDEX_FILE.format(env=self.environment)
            
            # メタデータを追加
            save_data = {
                "environment": self.environment,
                "fetched_at": datetime.now().isoformat(),
                "count": len(data),
                "data": data
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"マテリアルインデックスマスタ保存成功: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"マテリアルインデックスマスタ保存エラー: {e}")
            return False
    
    def save_tag_master(self, data: Dict[str, str]) -> bool:
        """
        タグマスタを保存
        
        Args:
            data: {コード: 名称} の辞書
        
        Returns:
            bool: 成功フラグ
        """
        try:
            filepath = self.master_data_dir / self.TAG_FILE.format(env=self.environment)
            
            # メタデータを追加
            save_data = {
                "environment": self.environment,
                "fetched_at": datetime.now().isoformat(),
                "count": len(data),
                "data": data
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"タグマスタ保存成功: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"タグマスタ保存エラー: {e}")
            return False
    
    def load_material_index_master(self) -> Tuple[bool, Dict[str, str]]:
        """
        マテリアルインデックスマスタを読み込み
        
        Returns:
            Tuple[bool, Dict[str, str]]: (成功フラグ, {コード: 名称} の辞書)
        """
        try:
            filepath = self.master_data_dir / self.MATERIAL_INDEX_FILE.format(env=self.environment)
            
            if not filepath.exists():
                logger.warning(f"マテリアルインデックスマスタファイルが存在しません: {filepath}")
                return False, {}
            
            with open(filepath, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            
            data = save_data.get("data", {})
            fetched_at = save_data.get("fetched_at", "不明")
            
            logger.info(f"マテリアルインデックスマスタ読み込み成功: {len(data)} 件 (取得日時: {fetched_at})")
            return True, data
            
        except Exception as e:
            logger.error(f"マテリアルインデックスマスタ読み込みエラー: {e}")
            return False, {}
    
    def load_tag_master(self) -> Tuple[bool, Dict[str, str]]:
        """
        タグマスタを読み込み
        
        Returns:
            Tuple[bool, Dict[str, str]]: (成功フラグ, {コード: 名称} の辞書)
        """
        try:
            filepath = self.master_data_dir / self.TAG_FILE.format(env=self.environment)
            
            if not filepath.exists():
                logger.warning(f"タグマスタファイルが存在しません: {filepath}")
                return False, {}
            
            with open(filepath, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            
            data = save_data.get("data", {})
            fetched_at = save_data.get("fetched_at", "不明")
            
            logger.info(f"タグマスタ読み込み成功: {len(data)} 件 (取得日時: {fetched_at})")
            return True, data
            
        except Exception as e:
            logger.error(f"タグマスタ読み込みエラー: {e}")
            return False, {}
    
    def get_master_info(self, master_type: str) -> Dict[str, any]:
        """
        マスタデータの情報を取得
        
        Args:
            master_type: "material_index" または "tag"
        
        Returns:
            Dict: マスタ情報 {exists: bool, count: int, fetched_at: str}
        """
        try:
            if master_type == "material_index":
                filepath = self.master_data_dir / self.MATERIAL_INDEX_FILE.format(env=self.environment)
            elif master_type == "tag":
                filepath = self.master_data_dir / self.TAG_FILE.format(env=self.environment)
            else:
                return {"exists": False, "count": 0, "fetched_at": None}
            
            if not filepath.exists():
                return {"exists": False, "count": 0, "fetched_at": None}
            
            with open(filepath, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            
            return {
                "exists": True,
                "count": save_data.get("count", 0),
                "fetched_at": save_data.get("fetched_at", "不明")
            }
            
        except Exception as e:
            logger.error(f"マスタ情報取得エラー: {e}")
            return {"exists": False, "count": 0, "fetched_at": None}
    
    def _save_debug_html(self, master_type: str, html_content: str):
        """
        デバッグ用にHTMLを保存
        
        Args:
            master_type: "material_index" または "tag"
            html_content: HTML内容
        """
        try:
            debug_dir = Path(get_dynamic_file_path("output/data_portal_debug"))
            debug_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"master_{master_type}_{self.environment}_{timestamp}.html"
            filepath = debug_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"デバッグHTML保存: {filepath}")
            
        except Exception as e:
            logger.error(f"デバッグHTML保存エラー: {e}")
    
    def _fetch_first_dataset(self) -> Tuple[bool, List[Dict]]:
        """
        既存データセットを1件取得
        
        Returns:
            Tuple[bool, List[Dict]]: (成功フラグ, データセットリスト)
        """
        try:
            logger.info("既存データセット一覧を取得中...")
            
            # データセット一覧ページにアクセス
            success, response = self.client.post(
                "main.php",
                data={
                    "mode": "theme",
                    "page": "1"
                }
            )
            
            if not success:
                logger.error("データセット一覧の取得に失敗")
                return False, []
            
            # HTMLをパース
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # データセット一覧からt_codeを抽出
            # hidden inputから取得: <input type="hidden" name="t_code" value="...">
            t_code_inputs = soup.find_all('input', {'type': 'hidden', 'name': 't_code'})
            
            if not t_code_inputs:
                logger.warning("データセットが見つかりませんでした")
                return False, []
            
            datasets = []
            for input_tag in t_code_inputs[:1]:  # 最初の1件のみ
                t_code = input_tag.get('value', '')
                if t_code:
                    datasets.append({'t_code': t_code})
            
            logger.info(f"データセット取得成功: {len(datasets)}件")
            return True, datasets
            
        except Exception as e:
            logger.error(f"データセット取得エラー: {e}", exc_info=True)
            return False, []
    
    def fetch_equipment_master_from_edit_page(self, t_code: str = None) -> Tuple[bool, Dict[str, str]]:
        """
        設備分類マスタを編集ページから取得してキャッシュ
        
        Args:
            t_code: データセットコード（省略時は既存のデータセットを使用）
        
        Returns:
            Tuple[bool, Dict[str, str]]: (成功フラグ, {コード: 名称} の辞書)
        """
        logger.info("設備分類マスタをポータル編集ページから取得...")
        
        try:
            # キャッシュ確認
            equipment_data = self.load_equipment_master()
            if equipment_data[0]:
                logger.info(f"設備分類マスタをキャッシュから読み込み: {len(equipment_data[1])}件")
                return equipment_data
            
            # t_codeが指定されていない場合、データセット一覧から1件取得
            if not t_code:
                logger.info("データセットコードが未指定のため、既存データセットを検索...")
                success, datasets = self._fetch_first_dataset()
                if success and datasets:
                    t_code = datasets[0].get('t_code', '')
                    logger.info(f"既存データセット使用: t_code={t_code}")
                else:
                    logger.warning("既存データセットが見つかりませんでした")
                    # t_codeなしで試行
                    t_code = ""
            
            # 編集ページにアクセス
            post_data = {
                "mode": "theme",
                "mode2": "change",
                "t_code": t_code,
                "keyword": "",
                "search_inst": "",
                "search_license_level": "",
                "search_status": "",
                "page": "1"
            }
            
            logger.info(f"編集ページアクセス: t_code={t_code}")
            
            success, response = self.client.post(
                "main.php",
                data=post_data
            )
            
            if not success:
                logger.error(f"編集ページアクセス失敗: {response}")
                return False, {}
            
            # デバッグ用にHTMLを保存
            self._save_debug_html("equipment", response.text)
            
            # HTMLから設備分類を抽出
            soup = BeautifulSoup(response.text, 'html.parser')
            equipment_map = {}
            
            # name="mec_code_array[]" のチェックボックスを探す
            equipment_checkboxes = soup.find_all('input', {'type': 'checkbox', 'name': 'mec_code_array[]'})
            
            for checkbox in equipment_checkboxes:
                value = checkbox.get('value', '')
                # ラベルを取得（for属性で紐づいたlabelタグから）
                checkbox_id = checkbox.get('id', '')
                label_tag = None
                
                if checkbox_id:
                    label_tag = soup.find('label', {'for': checkbox_id})
                
                if label_tag:
                    label = label_tag.get_text(strip=True)
                else:
                    # labelタグがない場合、次のlabelタグから取得
                    label_tag = checkbox.find_next('label')
                    if label_tag:
                        label = label_tag.get_text(strip=True)
                    else:
                        label = value
                
                if value and label:
                    equipment_map[value] = label
            
            logger.info(f"設備分類マスタ取得完了: {len(equipment_map)}件")
            
            # キャッシュ保存
            if equipment_map:
                self.save_equipment_master(equipment_map)
            
            return True, equipment_map
            
        except Exception as e:
            logger.error(f"設備分類マスタ取得エラー: {e}", exc_info=True)
            return False, {}
    
    def save_equipment_master(self, data: Dict[str, str]) -> bool:
        """
        設備分類マスタを保存
        
        Args:
            data: {コード: 名称} の辞書
        
        Returns:
            bool: 成功フラグ
        """
        try:
            filepath = self.master_data_dir / self.EQUIPMENT_FILE.format(env=self.environment)
            
            save_data = {
                "environment": self.environment,
                "fetched_at": datetime.now().isoformat(),
                "count": len(data),
                "data": data
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"設備分類マスタ保存成功: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"設備分類マスタ保存エラー: {e}")
            return False
    
    def load_equipment_master(self) -> Tuple[bool, Dict[str, str]]:
        """
        設備分類マスタを読み込み
        
        Returns:
            Tuple[bool, Dict[str, str]]: (成功フラグ, {コード: 名称} の辞書)
        """
        try:
            filepath = self.master_data_dir / self.EQUIPMENT_FILE.format(env=self.environment)
            
            if not filepath.exists():
                return False, {}
            
            with open(filepath, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            
            data = save_data.get("data", {})
            fetched_at = save_data.get("fetched_at", "不明")
            
            logger.info(f"設備分類マスタ読み込み成功: {len(data)} 件 (取得日時: {fetched_at})")
            return True, data
            
        except Exception as e:
            logger.error(f"設備分類マスタ読み込みエラー: {e}")
            return False, {}
