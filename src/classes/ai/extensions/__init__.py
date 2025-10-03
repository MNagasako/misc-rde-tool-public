"""
AI拡張機能パッケージ
"""

from .ai_extension_base import (
    AIPromptTemplate,
    AIExtensionBase,
    DatasetDescriptionExtension,
    AIExtensionRegistry
)

__all__ = [
    'AIPromptTemplate',
    'AIExtensionBase', 
    'DatasetDescriptionExtension',
    'AIExtensionRegistry'
]