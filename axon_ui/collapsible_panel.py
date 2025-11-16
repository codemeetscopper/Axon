"""Shared base class for collapsible overlay panels."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QMargins, Signal
from PySide6.QtWidgets import QFrame, QPushButton, QWidget


class CollapsiblePanel(QFrame):
    """Convenience base class for panels that can collapse to a toggle icon."""

    collapsedChanged = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._collapsed = True
        self._toggle_button: Optional[QPushButton] = None
        self._content_frame: Optional[QFrame] = None
        self._shadow = None

    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._apply_collapsed_state(collapsed)

    def expand(self) -> None:
        self.set_collapsed(False)

    def collapse(self) -> None:
        self.set_collapsed(True)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def _apply_collapsed_state(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setProperty("collapsed", "true" if collapsed else "false")
        if self.style() is not None:
            self.style().unpolish(self)
            self.style().polish(self)
        if self._content_frame is not None:
            self._content_frame.setVisible(not collapsed)
        self._on_collapse_state_changed()
        self.collapsedChanged.emit(collapsed)

    def _on_collapse_state_changed(self) -> None:
        self._apply_toggle_palette()
        self._update_toggle_icon()
        self._update_shadow()

    def _apply_toggle_palette(self) -> None:  # pragma: no cover - Qt painting
        pass

    def _update_toggle_icon(self) -> None:  # pragma: no cover - Qt painting
        pass

    def _update_shadow(self) -> None:  # pragma: no cover - Qt painting
        pass

    def collapsed_width(self) -> int:
        """Approximate the width occupied when only the toggle is visible."""

        layout = self.layout()
        if layout is None or self._toggle_button is None:
            return self.sizeHint().width()
        margins: QMargins = layout.contentsMargins()
        spacing = max(layout.spacing(), 0)
        toggle_width = self._toggle_button.sizeHint().width()
        return margins.left() + toggle_width + spacing + margins.right()
