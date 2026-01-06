"""Central coordinator for launching other widgets with the currently selected dataset.

This helper keeps track of the dataset payload that should be passed to another
widget (Data Fetch 2, Dataset Edit/Data Entry tabs, Data Register, ...), ensures
that the UI switches to the requested mode, and hands off the payload as soon as
the destination widget registers itself as a receiver.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any, Callable, Dict, Optional

from classes.managers.log_manager import get_logger

logger = get_logger(__name__)


@dataclass
class DatasetPayload:
    """Information required to re-select a dataset in another widget."""

    id: str
    display_text: str | None = None
    # Some widgets (e.g. dataset edit) require the full dataset dict, so we keep it
    # optional and pass through when available.
    raw: Optional[dict[str, Any]] = None


class DatasetLaunchManager:
    """Singleton helper that coordinates dataset handoff between widgets."""

    _RECENT_REAPPLY_WINDOW_SECONDS: float = 2.0

    _instance: "DatasetLaunchManager" | None = None

    _TARGET_MODE_MAP: Dict[str, str] = {
        "data_fetch2": "data_fetch2",
        "dataset_edit": "dataset_open",
        "dataset_dataentry": "dataset_open",
        "data_register": "data_register",
        "data_register_batch": "data_register",
    }

    def __init__(self) -> None:
        self._ui_controller: Any = None
        self._receivers: Dict[str, Callable[[DatasetPayload], bool]] = {}
        self._pending_request: Optional[dict[str, Any]] = None
        # Some screens can create the same target widget more than once during a
        # mode switch. Keep the most recently applied payload per target for a
        # short window so that the visible widget also receives it.
        self._recent_applied: Dict[str, tuple[DatasetPayload, float]] = {}

    # ------------------------------------------------------------------
    # Reset helpers (primarily for tests)
    # ------------------------------------------------------------------
    def reset_state(self) -> None:
        """Clear all runtime state.

        This is useful in long-running test sessions where widgets can be
        destroyed after other tests replaced the singleton instance.
        """

        self._ui_controller = None
        self._receivers.clear()
        self._pending_request = None
        self._recent_applied.clear()

    @classmethod
    def reset_instance(cls) -> None:
        """Drop the singleton instance and clear its state if present."""

        if cls._instance is not None:
            try:
                cls._instance.reset_state()
            except Exception:
                pass
        cls._instance = None

    # ------------------------------------------------------------------
    # Singleton helpers
    # ------------------------------------------------------------------
    @classmethod
    def instance(cls) -> "DatasetLaunchManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Registration API
    # ------------------------------------------------------------------
    def set_ui_controller(self, controller: Any) -> None:
        """Store a weak reference to the main UI controller."""

        self._ui_controller = controller
        logger.info("DatasetLaunchManager: UI controller registered (%s)", type(controller).__name__)

    def register_receiver(
        self,
        target_key: str,
        apply_callback: Callable[[DatasetPayload], bool],
    ) -> None:
        """Register a callback that can apply a pending dataset to a widget."""

        self._receivers[target_key] = apply_callback
        pending = self._pending_request
        pending_id = None
        if isinstance(pending, dict) and pending.get("target") == target_key:
            payload = pending.get("payload")
            if isinstance(payload, DatasetPayload):
                pending_id = payload.id
        logger.info(
            "DatasetLaunchManager: receiver registered target=%s (pending=%s)",
            target_key,
            pending_id or "-",
        )
        if self._try_apply(target_key):
            return

        recent = self._recent_applied.get(target_key)
        if recent is None:
            return
        payload, applied_at = recent
        if time.monotonic() - applied_at > self._RECENT_REAPPLY_WINDOW_SECONDS:
            return
        try:
            logger.info(
                "DatasetLaunchManager: reapplying recent payload target=%s dataset=%s",
                target_key,
                payload.id,
            )
            apply_callback(payload)
        except Exception:  # pragma: no cover - defensive logging
            logger.debug("DatasetLaunchManager: recent payload reapply failed", exc_info=True)

    def unregister_receiver(self, target_key: str) -> None:
        self._receivers.pop(target_key, None)
        logger.debug("DatasetLaunchManager: receiver removed for %s", target_key)

    # ------------------------------------------------------------------
    # Launch API
    # ------------------------------------------------------------------
    def request_launch(
        self,
        *,
        target_key: str,
        dataset_id: str,
        display_text: str | None = None,
        raw_dataset: Optional[dict[str, Any]] = None,
        source_name: str | None = None,
    ) -> bool:
        """Store a dataset payload and switch the UI to the requested target."""

        if not dataset_id:
            logger.warning("DatasetLaunchManager: dataset_id is missing for %s", target_key)
            return False

        payload = DatasetPayload(id=dataset_id, display_text=display_text, raw=raw_dataset)
        self._pending_request = {
            "target": target_key,
            "payload": payload,
            "source": source_name,
        }
        logger.info(
            "DatasetLaunchManager: launch requested target=%s dataset=%s", target_key, dataset_id
        )

        self._ensure_target_mode(target_key)
        applied = self._try_apply(target_key)
        if not applied and self._pending_request is None:
            applied = True
        if not applied:
            logger.info(
                "DatasetLaunchManager: launch pending target=%s dataset=%s receivers=%s",
                target_key,
                dataset_id,
                sorted(self._receivers.keys()),
            )
        if applied:
            self._notify_status(
                f"{display_text or dataset_id} を {self._resolve_mode_label(target_key)} へ連携しました"
            )
        return applied

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _try_apply(self, target_key: str) -> bool:
        """Apply pending payload if the receiver for *target_key* is ready."""

        if not self._pending_request:
            return False
        if self._pending_request.get("target") != target_key:
            return False

        callback = self._receivers.get(target_key)
        if not callback:
            return False

        payload: DatasetPayload = self._pending_request["payload"]
        try:
            logger.info(
                "DatasetLaunchManager: applying payload target=%s dataset=%s",
                target_key,
                payload.id,
            )
            applied = callback(payload)
            if applied:
                logger.debug(
                    "DatasetLaunchManager: payload consumed by %s (dataset=%s)",
                    target_key,
                    payload.id,
                )
                self._recent_applied[target_key] = (payload, time.monotonic())
                self._pending_request = None
                return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("DatasetLaunchManager: receiver for %s failed: %s", target_key, exc)
        return False

    def _ensure_target_mode(self, target_key: str) -> None:
        mode = self._TARGET_MODE_MAP.get(target_key)
        controller = self._ui_controller
        if not mode or not controller:
            if not controller:
                logger.info(
                    "DatasetLaunchManager: ui_controller is not set (cannot switch to %s for target=%s)",
                    mode or "-",
                    target_key,
                )
            return

        try:
            logger.debug("DatasetLaunchManager: switch_mode(%s) for target=%s", mode, target_key)
            controller.switch_mode(mode)
            focus_func = getattr(controller, "focus_dataset_launch_target", None)
            if callable(focus_func):
                try:
                    focus_func(target_key)
                except Exception:  # pragma: no cover - defensive logging
                    logger.debug("DatasetLaunchManager: focus_dataset_launch_target failed", exc_info=True)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("DatasetLaunchManager: switch_mode failed: %s", exc)

    def _resolve_mode_label(self, target_key: str) -> str:
        if target_key == "data_fetch2":
            return "データ取得2"
        if target_key == "dataset_edit":
            return "データセット修正"
        if target_key == "dataset_dataentry":
            return "データセット エントリー"
        if target_key == "data_register":
            return "データ登録"
        if target_key == "data_register_batch":
            return "データ登録(一括)"
        return target_key

    def _notify_status(self, message: str) -> None:
        controller = self._ui_controller
        parent = getattr(controller, "parent", None)
        display_manager = getattr(parent, "display_manager", None)
        if hasattr(display_manager, "set_message"):
            try:
                display_manager.set_message(message)
            except Exception:  # pragma: no cover - defensive
                logger.debug("DatasetLaunchManager: display_manager update failed", exc_info=True)


__all__ = ["DatasetLaunchManager", "DatasetPayload"]
