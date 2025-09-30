"""
サブグループAPI クライアント（リファクタリング版）
HTTP通信、認証、ペイロード構築を統一管理
"""
import json
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer


class SubgroupApiClient:
    """サブグループAPI通信クライアント"""
    
    def __init__(self, widget):
        """
        Args:
            widget: 親ウィジェット（bearer_token取得用）
        """
        self.widget = widget
        self.api_base_url = "https://rde-api.nims.go.jp"
        self.bearer_token = None
    
    def authenticate(self):
        """
        Bearer トークンの取得・設定
        
        Returns:
            bool: 認証成功かどうか
        """
        self.bearer_token = self._find_bearer_token()
        if not self.bearer_token:
            QMessageBox.warning(
                self.widget, 
                "認証エラー", 
                "Bearerトークンが取得できません。ログイン状態を確認してください。"
            )
            return False
        return True
    
    def _find_bearer_token(self):
        """widgetまたは親階層からbearer_tokenを探す"""
        current = self.widget
        # QWidgetのparent()はQObjectを返すので、bearer_token属性をたどる
        while current is not None:
            token = getattr(current, 'bearer_token', None)
            if token:
                return token
            # PyQt: parent()はQObject、Noneまたはcallable
            if hasattr(current, 'parent'):
                p = current.parent()
                if p is not None and p != current:
                    current = p
                else:
                    break
            else:
                break
        return None
    
    def create_subgroup(self, payload, group_name, auto_refresh=True):
        """
        サブグループ作成API呼び出し
        
        Args:
            payload (dict): APIペイロード
            group_name (str): グループ名（メッセージ用）
            auto_refresh (bool): 成功時の自動リフレッシュ有効/無効
            
        Returns:
            bool: 作成成功かどうか
        """
        if not self.authenticate():
            return False
        
        api_url = f"{self.api_base_url}/groups"
        headers = self._build_headers()
        
        try:
            from net.http_helpers import proxy_post
            resp = proxy_post(api_url, headers=headers, json=payload, timeout=15)
            return self._handle_response(resp, group_name, "作成", auto_refresh)
        except Exception as e:
            QMessageBox.warning(self.widget, "APIエラー", f"API送信中にエラーが発生しました: {e}")
            return False
    
    def update_subgroup(self, group_id, payload, group_name, auto_refresh=True):
        """
        サブグループ更新API呼び出し
        
        Args:
            group_id (str): グループID
            payload (dict): APIペイロード
            group_name (str): グループ名（メッセージ用）
            auto_refresh (bool): 成功時の自動リフレッシュ有効/無効
            
        Returns:
            bool: 更新成功かどうか
        """
        if not self.authenticate():
            return False
        
        api_url = f"{self.api_base_url}/groups/{group_id}"
        headers = self._build_headers()
        
        try:
            from net.http_helpers import proxy_patch
            resp = proxy_patch(api_url, headers=headers, json=payload, timeout=15)
            return self._handle_response(resp, group_name, "更新", auto_refresh)
        except Exception as e:
            QMessageBox.warning(self.widget, "APIエラー", f"API送信中にエラーが発生しました: {e}")
            return False
    
    def _build_headers(self):
        """標準HTTPヘッダーの構築"""
        return {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Authorization": f"Bearer {self.bearer_token}",
            "Connection": "keep-alive",
            "Content-Type": "application/vnd.api+json",
            "Host": "rde-api.nims.go.jp",
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
    
    def _handle_response(self, response, group_name, operation, auto_refresh):
        """APIレスポンスのハンドリング"""
        if response.status_code in (200, 201):
            QMessageBox.information(
                self.widget, 
                f"{operation}成功", 
                f"サブグループ[{group_name}]の{operation}に成功しました。"
            )
            
            # 成功時にsubGroup.jsonを自動再取得
            if auto_refresh:
                self._schedule_auto_refresh()
            
            return True
        else:
            QMessageBox.warning(
                self.widget, 
                f"{operation}失敗", 
                f"サブグループ[{group_name}]の{operation}に失敗しました。\n\n"
                f"Status: {response.status_code}\n{response.text}"
            )
            return False
    
    def _schedule_auto_refresh(self):
        """自動リフレッシュのスケジューリング"""
        try:
            def auto_refresh():
                try:
                    from classes.basic.core.basic_info_logic import auto_refresh_subgroup_json
                    from classes.utils.progress_worker import SimpleProgressWorker
                    from classes.basic.ui.ui_basic_info import show_progress_dialog
                    
                    worker = SimpleProgressWorker(
                        auto_refresh_subgroup_json,
                        "サブグループ情報を更新中..."
                    )
                    show_progress_dialog(self.widget, worker)
                    
                    # サブグループ更新通知を送信
                    try:
                        from classes.dataset.util.dataset_refresh_notifier import get_subgroup_refresh_notifier
                        subgroup_notifier = get_subgroup_refresh_notifier()
                        # 更新完了後に少し遅延して通知
                        from PyQt5.QtCore import QTimer
                        def send_notification():
                            try:
                                subgroup_notifier.notify_refresh()
                                print("[INFO] サブグループ更新通知を送信しました")
                            except Exception as e:
                                print(f"[WARNING] サブグループ更新通知送信に失敗: {e}")
                        QTimer.singleShot(2000, send_notification)  # 2秒後に通知
                    except Exception as e:
                        print(f"[WARNING] サブグループ更新通知の設定に失敗: {e}")
                        
                except Exception as e:
                    print(f"[WARNING] サブグループ情報自動更新に失敗: {e}")
            
            QTimer.singleShot(1000, auto_refresh)
        except Exception as e:
            print(f"[WARNING] サブグループ情報自動更新の設定に失敗: {e}")


class SubgroupPayloadBuilder:
    """サブグループAPIペイロード構築クラス"""
    
    @staticmethod
    def create_payload(group_name, description, subjects, funds, roles, parent_id):
        """
        新規作成用ペイロードの構築
        
        Args:
            group_name (str): グループ名
            description (str): 説明
            subjects (list): 課題リスト [{"grantNumber": "", "title": ""}, ...]
            funds (list): 研究資金リスト [str, ...]
            roles (list): ロールリスト [{"userId": "", "role": "", ...}, ...]
            parent_id (str): 親グループID
            
        Returns:
            dict: APIペイロード
        """
        # 研究資金をAPIフォーマットに変換
        formatted_funds = [{"fundNumber": f} for f in funds if f.strip()]
        
        return {
            "data": {
                "type": "group",
                "attributes": {
                    "name": group_name,
                    "description": description,
                    "subjects": subjects,
                    "funds": formatted_funds,
                    "roles": roles
                },
                "relationships": {
                    "parent": {
                        "data": {
                            "type": "group",
                            "id": parent_id
                        }
                    }
                }
            }
        }
    
    @staticmethod
    def update_payload(group_id, group_name, description, subjects, funds, roles, parent_id):
        """
        更新用ペイロードの構築（PATCH用）
        
        Args:
            group_id (str): グループID
            group_name (str): グループ名
            description (str): 説明
            subjects (list): 課題リスト
            funds (list): 研究資金リスト
            roles (list): ロールリスト
            parent_id (str): 親グループID
            
        Returns:
            dict: APIペイロード
        """
        # 研究資金をAPIフォーマットに変換
        formatted_funds = [{"fundNumber": f} for f in funds if f.strip()]
        
        return {
            "data": {
                "type": "group",
                "id": group_id,
                "attributes": {
                    "name": group_name,
                    "description": description,
                    "subjects": subjects,
                    "funds": formatted_funds,
                    "roles": roles
                },
                "relationships": {
                    "parent": {
                        "data": {
                            "type": "group",
                            "id": parent_id
                        }
                    }
                }
            }
        }
    
    @staticmethod
    def build_request_info(payload, group_name, operation_type="作成"):
        """
        リクエスト情報文字列の構築（確認ダイアログ用）
        
        Args:
            payload (dict): APIペイロード
            group_name (str): グループ名
            operation_type (str): 操作タイプ（"作成" または "更新"）
            
        Returns:
            str: リクエスト情報文字列
        """
        attr = payload['data']['attributes']
        
        # ロール情報の簡易表示
        role_summary = []
        for role in attr.get('roles', []):
            user_id = role.get('userId', '')
            role_name = role.get('role', '')
            role_summary.append(f"{user_id}({role_name})")
        
        return (
            f"本当にサブグループを{operation_type}しますか？\n\n"
            f"グループ名: {attr.get('name')}\n"
            f"説明: {attr.get('description')}\n"
            f"課題数: {len(attr.get('subjects', []))}\n"
            f"研究資金数: {len(attr.get('funds', []))}\n"
            f"メンバー数: {len(attr.get('roles', []))}\n"
            f"ロール: {', '.join(role_summary[:3])}{'...' if len(role_summary) > 3 else ''}\n"
            f"\nこの操作はARIMデータポータルでサブグループを{operation_type}します。"
        )
    
    @staticmethod
    def build_detailed_request_info(payload, api_url):
        """
        詳細リクエスト情報の構築（デバッグ・詳細表示用）
        
        Args:
            payload (dict): APIペイロード
            api_url (str): API URL
            
        Returns:
            str: 詳細リクエスト情報
        """
        headers_dict = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Authorization": f"Bearer <YOUR_BEARER_TOKEN>",
            "Connection": "keep-alive",
            "Content-Type": "application/vnd.api+json",
            "Host": "rde-api.nims.go.jp",
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        
        header_order = [
            "Accept", "Accept-Encoding", "Accept-Language", "Authorization", "Connection",
            "Content-Type", "Host", "Origin", "Referer", "Sec-Fetch-Dest", "Sec-Fetch-Mode",
            "Sec-Fetch-Site", "User-Agent", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"
        ]
        headers_str = '\n'.join([f'{k}: {headers_dict[k]}' for k in header_order if k in headers_dict])
        payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
        
        return (
            f"Request URL\n{api_url}\nRequest Method\nPOST\n\n"
            f"POST /groups HTTP/1.1\n{headers_str}\n\n{payload_str}"
        )


# 後方互換性のための関数群（既存コードとの互換性維持）

def find_bearer_token(widget):
    """
    後方互換性のためのbearer_token取得関数
    """
    client = SubgroupApiClient(widget)
    return client._find_bearer_token()


def send_subgroup_request(widget, api_url, headers, payload, group_name, auto_refresh=True):
    """
    後方互換性のためのサブグループリクエスト送信関数
    """
    client = SubgroupApiClient(widget)
    if "groups" in api_url and headers.get("Authorization"):
        # 新規作成の場合
        return client.create_subgroup(payload, group_name, auto_refresh)
    else:
        # その他の場合（要実装）
        print(f"[WARNING] 未対応のAPIリクエスト: {api_url}")
        return False


def create_subgroup_payload(group_name, description, subjects, funds, roles, parent_id):
    """
    後方互換性のためのペイロード作成関数
    """
    return SubgroupPayloadBuilder.create_payload(
        group_name, description, subjects, funds, roles, parent_id
    )


def build_subgroup_request(info, group_config, member_lines, idx, group, selected_user_ids=None, roles=None):
    """
    後方互換性のためのリクエスト構築関数（一括作成用）
    """
    # 既存の実装を維持（将来的にはSubgroupPayloadBuilderに統合予定）
    raw_subjects = group.get("subjects", [])
    subjects = []
    for s in raw_subjects:
        if isinstance(s, dict):
            grant_number = s.get("grantNumber")
            title = s.get("title")
            if not grant_number and not title:
                continue
            if not grant_number:
                grant_number = title
            if not title:
                title = grant_number
            subjects.append({"grantNumber": grant_number, "title": title})
        else:
            grant_number = str(s)
            subjects.append({"grantNumber": grant_number, "title": grant_number})
    
    raw_funds = group.get("funds", [])
    funds = []
    for f in raw_funds:
        if isinstance(f, dict):
            fund_number = f.get("fundNumber")
            if fund_number:
                funds.append({"fundNumber": fund_number})
        else:
            fund_number = str(f)
            if fund_number:
                funds.append({"fundNumber": fund_number})
    
    # rolesが提供されていればそれを使用、なければ旧方式
    if roles:
        payload_roles = roles
    elif selected_user_ids:
        payload_roles = []
        for user_id in selected_user_ids:
            payload_roles.append({
                "userId": user_id,
                "role": "OWNER",
                "canCreateDatasets": True,
                "canEditMembers": True
            })
    else:
        payload_roles = []
    
    parent_id = info.get("project_group_id", "")
    payload = {
        "data": {
            "type": "group",
            "attributes": {
                "name": group.get("group_name", ""),
                "description": group.get("description", ""),
                "subjects": subjects,
                "funds": funds,
                "roles": payload_roles
            },
            "relationships": {
                "parent": {
                    "data": {
                        "type": "group",
                        "id": parent_id
                    }
                }
            }
        }
    }
    
    api_url = "https://rde-api.nims.go.jp/groups"
    return SubgroupPayloadBuilder.build_detailed_request_info(payload, api_url), payload, api_url, {}
