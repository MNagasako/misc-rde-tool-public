"""
新データツリー管理モジュール - ARIM RDE Tool
- datatree.json（新構造）を作成・更新・参照するためのクラス
- 既存のdatatree.jsonとは独立して動作し、干渉しない
- ドキュメント記載のツリー構造（grant_number→datasets→details→images）に準拠
"""
import json
import os
import logging
from typing import Any, Dict, List, Optional
from functions.utils import sanitize_path_name

class DataTreeManager:
    def __init__(self, file_path: str, logger: logging.Logger = None):
        self.file_path = file_path
        self.logger = logger or logging.getLogger("DataTreeManager")
        self.data = self._load() or {"grantNumber": []}
        if not os.path.exists(self.file_path):
            try:
                self.save()
                self.logger.info(f"[DataTreeManager] 新規データツリーを作成: {self.file_path}")
            except Exception as e:
                self.logger.error(f"[DataTreeManager] データツリー初期化失敗: {e}")
        else:
            self.logger.info(f"[DataTreeManager] 既存データツリーをロード: {self.file_path}")

    def _load(self) -> Optional[dict]:
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, encoding="utf-8") as f:
                    data = json.load(f)
                    self.logger.info(f"[DataTreeManager] データツリーをロード: {self.file_path}")
                    return data
        except Exception as e:
            self.logger.error(f"[DataTreeManager] データツリーロード失敗: {e}")
        return None

    def save(self):
        try:
            dirpath = os.path.dirname(self.file_path)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"[DataTreeManager] データツリーを保存: {self.file_path}")
        except Exception as e:
            self.logger.error(f"[DataTreeManager] データツリー保存失敗: {e}")

    def get_grant(self, grant_id: str) -> Optional[dict]:
        for grant in self.data["grantNumber"]:
            if grant["id"] == grant_id:
                return grant
        return None

    def add_or_update_grant(self, grant_id: str, name: str = None, subject_title: str = None, type_name: str = "grant") -> dict:
        grant = self.get_grant(grant_id)
        if grant:
            if name:
                grant["name"] = name
            if subject_title:
                grant["title"] = subject_title
            grant["type"] = type_name
        else:
            grant = {
                "type": type_name,
                "id": grant_id,
                "name": name or grant_id,
                #"title": subject_title or name or grant_id,
                "datasets": []
            }
            self.data["grantNumber"].append(grant)
            self.logger.info(f"[DataTreeManager] grant id={grant_id} を新規追加")
        self.save()
        return grant

    def get_dataset(self, grant_id: str, dataset_id: str) -> Optional[dict]:
        grant = self.get_grant(grant_id)
        if not grant:
            return None
        for ds in grant["datasets"]:
            if ds["id"] == dataset_id:
                return ds
        return None

    def add_or_update_dataset(self, grant_id: str, dataset_id: str, name: str = None, subdir: str = None, type_name: str = "dataset") -> dict:
        grant = self.get_grant(grant_id)
        if not grant:
            raise ValueError(f"grant id {grant_id} not found")
        ds = self.get_dataset(grant_id, dataset_id)
        if ds:
            if name:
                ds["name"] = name
            ds["type"] = type_name
            if subdir:
                ds["subdir"] = subdir
        else:
            ds = {
                "type": type_name,
                "id": dataset_id,
                "name": name or dataset_id,
                "subdir": subdir or "",
                "details": []
            }
            grant["datasets"].append(ds)
        self.save()
        return ds

    def get_detail(self, grant_id: str, dataset_id: str, detail_id: str) -> Optional[dict]:
        ds = self.get_dataset(grant_id, dataset_id)
        if not ds:
            return None
        for detail in ds["details"]:
            if detail["id"] == detail_id:
                return detail
        return None

    def add_or_update_detail(self, grant_id: str, dataset_id: str, detail_id: str, name: str = None, title: str = None, description: str = None, subdir: str = None, type_name: str = "detail") -> dict:
        ds = self.get_dataset(grant_id, dataset_id)
        if not ds:
            raise ValueError(f"dataset id {dataset_id} not found")
        detail = self.get_detail(grant_id, dataset_id, detail_id)
        if detail:
            if name:
                detail["name"] = name
            if title:
                detail["title"] = title
            if description:
                detail["description"] = description
            if subdir:
                detail["subdir"] = subdir
            detail["type"] = type_name
        else:
            detail = {
                "type": type_name,
                "id": detail_id,
                "name": name or detail_id,
                #"title": title or name or detail_id,
                "description": description or "",
                "subdir": subdir or "",
                "images": []
            }
            ds["details"].append(detail)
        self.save()
        return detail

    def add_image_to_detail(self, grant_id: str, dataset_id: str, detail_id: str, image_id: str, name: str = None, type_name: str = "image") -> dict:
        detail = self.get_detail(grant_id, dataset_id, detail_id)
        if not detail:
            raise ValueError(f"detail id {detail_id} not found")
        if "images" not in detail:
            detail["images"] = []
        for img in detail["images"]:
            if img["id"] == image_id:
                if name:
                    img["name"] = name
                img["type"] = type_name
                return img
        img = {"type": type_name, "id": image_id, "name": name or image_id}
        detail["images"].append(img)
        self.save()
        return img

    def get_tree(self) -> dict:
        return self.data

    def reload(self):
        self.data = self._load() or {"grantNumber": []}

    def get_dataset_id_by_detail_id(self, detail_id: str) -> Optional[str]:
        for grant in self.data["grantNumber"]:
            for dataset in grant["datasets"]:
                for detail in dataset["details"]:
                    if detail["id"] == detail_id:
                        return dataset["id"]
        return None

    def get_dataset_id_by_image_id(self, image_id: str) -> Optional[str]:
        for grant in self.data["grantNumber"]:
            for dataset in grant["datasets"]:
                for detail in dataset["details"]:
                    for image in detail.get("images", []):
                        if image["id"] == image_id:
                            return dataset["id"]
        return None

    def get_detail_by_image_id(self, image_id: str) -> Optional[dict]:
        for grant in self.data["grantNumber"]:
            for dataset in grant["datasets"]:
                for detail in dataset["details"]:
                    for image in detail.get("images", []):
                        if image["id"] == image_id:
                            return detail
        return None

    def get_grant_id_by_detail_id(self, detail_id: str) -> Optional[str]:
        for grant in self.data["grantNumber"]:
            for dataset in grant["datasets"]:
                for detail in dataset["details"]:
                    if detail["id"] == detail_id:
                        return grant["id"]
        return None

    def get_grant_id_by_image_id(self, image_id: str) -> Optional[str]:
        for grant in self.data["grantNumber"]:
            for dataset in grant["datasets"]:
                for detail in dataset["details"]:
                    for image in detail.get("images", []):
                        if image["id"] == image_id:
                            return grant["id"]
        return None

    def get_grant_id_by_dataset_id(self, dataset_id: str) -> Optional[str]:
        for grant in self.data["grantNumber"]:
            for dataset in grant["datasets"]:
                if dataset["id"] == dataset_id:
                    return grant["id"]
        return None

    def get_datasets_by_grant_id(self, grant_id: str) -> Optional[List[dict]]:
        grant = self.get_grant(grant_id)
        if grant:
            return grant.get("datasets", [])
        return []

    def get_details_by_dataset_id(self, dataset_id: str) -> Optional[List[dict]]:
        dataset_ids=[]
        with open(self.file_path, encoding="utf-8") as f:
            datatree = json.load(f)
            # grantNumberはリスト形式なのでループで処理
            for grant in datatree.get("grantNumber", []):
                for dataset in grant["datasets"]:
                    if dataset.get("id") == dataset_id:
                        for detail in dataset.get("details", []):
                            if detail.get("type") =="detail" :
                                dataset_ids.append(detail.get("id"))
        return dataset_ids

    def get_images_by_detail_id(self, detail_id: str) -> Optional[List[dict]]:
        for grant in self.data["grantNumber"]:
            for dataset in grant["datasets"]:
                for detail in dataset["details"]:
                    if detail["id"] == detail_id:
                        return detail.get("images", [])
        return []
    
    def get_subdir_from_new_datatree(self, data_id, grant_number=None):
        """
        新データツリーからsubdirを取得し、nameと連結してサブディレクトリのパスを返す。
        grant_numberが指定された場合、そのgrantNumber内のみを検索する。
        grant_numberがNoneの場合、全grantNumber横断で検索する。
        """
        try:
            with open(self.file_path, encoding="utf-8") as f:
                datatree = json.load(f)
                for grant in datatree.get("grantNumber", []):
                    grant_id = sanitize_path_name(grant.get("id", "unknown"))
                    
                    # grant_numberが指定されている場合、マッチするgrantNumberのみを検索
                    if grant_number and grant_id != grant_number:
                        continue
                    
                    grant_name = sanitize_path_name(grant.get("name", "unknown"))
                    for dataset in grant.get("datasets", []):
                        dataset_name = sanitize_path_name(dataset.get("name", "unknown"))
                        for detail in dataset.get("details", []):
                            if detail.get("id") == data_id:
                                detail_name = sanitize_path_name(detail.get("name", "unknown"))
                                result_path = os.path.join(grant_id, dataset_name, detail_name)
                                if grant_number:
                                    self.logger.info(f"[PATH] data_id={data_id}, grant_number={grant_number} -> {result_path}")
                                else:
                                    self.logger.info(f"[PATH] data_id={data_id}, 全検索 -> {result_path} (所属grant: {grant_id})")
                                self.logger.debug(f"[PATH] 詳細: grant_id={grant_id}, dataset_name={dataset_name}, detail_name={detail_name}")
                                return result_path
                
                # 指定されたgrant_number内に見つからなかった場合
                if grant_number:
                    self.logger.warning(f"データID {data_id} が grantNumber {grant_number} 内に存在しません。")
                else:
                    self.logger.warning(f"データID {data_id} がどのgrantNumberにも存在しません。")
                
                # デバッグ用：利用可能なdata_idを出力
                if grant_number:
                    self.logger.debug(f"[PATH] 利用可能なdata_id一覧を確認中 (grant_number={grant_number})...")
                    available_ids = []
                    for grant in datatree.get("grantNumber", []):
                        if sanitize_path_name(grant.get("id", "unknown")) != grant_number:
                            continue
                        for dataset in grant.get("datasets", []):
                            for detail in dataset.get("details", []):
                                available_ids.append(detail.get("id"))
                    self.logger.debug(f"[PATH] 利用可能なdata_id (grant_number={grant_number}): {available_ids[:10]}...")  # 最初の10件のみ
                return None
        except Exception as e:
            self.logger.warning(f"新データツリーからsubdir取得失敗: {e}")
            return None
