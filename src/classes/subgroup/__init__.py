"""
サブグループ機能モジュール

このモジュールは、サブグループの作成・修正機能を提供します。

標準構成:
- core/: メインロジック（APIアクセス、データ操作）
- ui/: Widget作成・画面構築
- util/: 便利機能やヘルパー（機能内でのみ使用）
- conf/: 設定・デザイン・文言などの定義
"""

# Core機能
from .core.subgroup_api_client import SubgroupApiClient
from .core.subgroup_data_manager import SubgroupDataManager
from .core import subgroup_api_helper  # 関数群

# UI機能
from .ui.subgroup_create_widget import create_subgroup_create_widget
from .ui.subgroup_edit_widget import EditFormManager, EditMemberManager
from .ui.subgroup_subject_widget import SubjectEntryWidget

# Utility機能
from .util.subgroup_member_selector_common import CommonSubgroupMemberSelector, create_common_subgroup_member_selector
from .util.subgroup_ui_helpers import (
    load_user_entries, SubgroupFormBuilder, SubgroupCreateHandler,
    MemberDataProcessor, show_selected_user_ids, prepare_subgroup_create_request
)
from .util.subgroup_validators import (
    SubjectInputValidator, UserRoleValidator, FormValidator, 
    UIValidator, SubgroupFilterValidator
)

__all__ = [
    # Core
    "SubgroupApiClient",
    "SubgroupDataManager",
    "subgroup_api_helper",
    # UI
    "create_subgroup_create_widget",
    "EditFormManager",
    "EditMemberManager", 
    "SubjectEntryWidget",
    # Util
    "CommonSubgroupMemberSelector",
    "create_common_subgroup_member_selector",
    "load_user_entries",
    "SubgroupFormBuilder",
    "SubgroupCreateHandler",
    "MemberDataProcessor",
    "show_selected_user_ids",
    "prepare_subgroup_create_request",
    "SubjectInputValidator",
    "UserRoleValidator", 
    "FormValidator",
    "UIValidator",
    "SubgroupFilterValidator"
]
