"""Utility class for managing AI extension button definitions."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional
import logging

from classes.dataset.util.ai_extension_helper import (
    load_ai_extension_config,
    save_ai_extension_config,
    infer_ai_suggest_target_kind,
)

logger = logging.getLogger(__name__)


class AIExtensionConfigManager:
    """In-memory manager for AI extension button definitions."""

    def __init__(self, config_data: Optional[Dict[str, Any]] = None):
        self._config_data = copy.deepcopy(config_data) if config_data else load_ai_extension_config()
        self._buttons: List[Dict[str, Any]] = self._normalize(self._config_data.get('buttons', []))
        self._default_buttons: List[Dict[str, Any]] = self._normalize(
            self._config_data.get('default_buttons', [])
        )
        logger.debug("AIExtensionConfigManager initialized: %s buttons", len(self._buttons))

    @staticmethod
    def _normalize(buttons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for entry in buttons:
            cloned = copy.deepcopy(entry)
            if 'allow_delete' not in cloned:
                cloned['allow_delete'] = False
            if 'output_format' not in cloned:
                cloned['output_format'] = 'text'
            if 'target_kind' not in cloned:
                cloned['target_kind'] = infer_ai_suggest_target_kind(cloned)
            normalized.append(cloned)
        return normalized

    @property
    def buttons(self) -> List[Dict[str, Any]]:
        return self._buttons

    def build_config(self) -> Dict[str, Any]:
        config = copy.deepcopy(self._config_data)
        config['buttons'] = copy.deepcopy(self._buttons)
        config['default_buttons'] = copy.deepcopy(self._default_buttons)
        return config

    def find_by_id(self, button_id: str) -> Optional[int]:
        for idx, button in enumerate(self._buttons):
            if button.get('id') == button_id:
                return idx
        return None

    def add_button(self, button_id: str, template: Optional[Dict[str, Any]] = None) -> int:
        if not button_id or not button_id.strip():
            raise ValueError("button_id must not be empty")
        if self.find_by_id(button_id) is not None:
            raise ValueError(f"Button ID '{button_id}' is already defined")

        base = copy.deepcopy(template) if template else {}
        base.update({
            'id': button_id,
            'label': base.get('label') or button_id,
            'description': base.get('description') or '',
            'prompt_file': base.get('prompt_file') or '',
            'icon': base.get('icon') or '🤖',
            'category': base.get('category') or 'カスタム',
            'output_format': base.get('output_format') or 'text',
        })
        base['allow_delete'] = True
        self._buttons.append(base)
        logger.debug("Added AI extension button: %s", button_id)
        return len(self._buttons) - 1

    def remove_button(self, index: int) -> Dict[str, Any]:
        self._validate_index(index)
        button = self._buttons[index]
        if not button.get('allow_delete', False):
            raise ValueError("This button is locked and cannot be removed")
        removed = self._buttons.pop(index)
        logger.debug("Removed AI extension button: %s", removed.get('id'))
        return removed

    def move_button(self, source_index: int, target_index: int) -> bool:
        self._validate_index(source_index)
        if target_index < 0 or target_index >= len(self._buttons):
            return False
        if source_index == target_index:
            return False
        button = self._buttons.pop(source_index)
        self._buttons.insert(target_index, button)
        logger.debug("Moved AI extension button %s -> %s", source_index, target_index)
        return True

    def can_delete(self, index: int) -> bool:
        self._validate_index(index)
        return bool(self._buttons[index].get('allow_delete', False))

    def save(self) -> bool:
        payload = self.build_config()
        return save_ai_extension_config(payload)

    def _validate_index(self, index: int) -> None:
        if index < 0 or index >= len(self._buttons):
            raise IndexError("Button index is out of range")
