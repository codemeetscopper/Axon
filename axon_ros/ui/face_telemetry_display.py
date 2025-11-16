"""Composite widget that overlays telemetry and info panels on the face widget."""

from __future__ import annotations

from functools import partial
from typing import Sequence

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel


class FaceTelemetryDisplay(QWidget):
    """Composite widget that overlays telemetry/info controls on the face widget."""

    def __init__(
        self,
        face: RoboticFaceWidget,
        overlays: Sequence[QWidget] | QWidget,
        parent: QWidget | None = None,
        fixed_size: QSize | Sequence[int] | None = QSize(800, 480),
    ) -> None:
        super().__init__(parent)
        self._face = face
        if isinstance(overlays, Sequence):
            self._overlay_widgets = tuple(overlays)
        else:
            self._overlay_widgets = (overlays,)
        self._fixed_size = fixed_size
        self._collapsible_panels: list[QWidget] = []
        self._telemetry_panel = next(
            (widget for widget in self._overlay_widgets if isinstance(widget, TelemetryPanel)),
            None,
        )
        self._info_panel = next(
            (widget for widget in self._overlay_widgets if isinstance(widget, InfoPanel)),
            None,
        )
        self._overlay_dock: QWidget | None = None
        self._dock_layout: QHBoxLayout | None = None
        self._overlay_margin = 16
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("robotScreen")
        if self._fixed_size is not None:
            if isinstance(self._fixed_size, QSize):
                size = self._fixed_size
            else:
                width, height = self._fixed_size
                size = QSize(int(width), int(height))
            self.setFixedSize(size)
        else:
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        stack = QStackedLayout(self)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(0)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        face_layer = QFrame(self)
        face_layer.setObjectName("robotScreenFace")
        face_layout = QVBoxLayout(face_layer)
        face_layout.setContentsMargins(0, 0, 0, 0)
        face_layout.setSpacing(0)
        self._face.setParent(face_layer)
        self._face.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        face_layout.addWidget(self._face)
        stack.addWidget(face_layer)

        overlay = QWidget(self)
        overlay.setObjectName("robotScreenOverlay")
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(
            self._overlay_margin, self._overlay_margin, self._overlay_margin, self._overlay_margin
        )
        overlay_layout.setSpacing(0)

        dock = QWidget(overlay)
        dock_layout = QHBoxLayout(dock)
        dock_layout.setContentsMargins(0, 0, 0, 0)
        dock_layout.setSpacing(10)
        dock_layout.addStretch(1)
        for widget in self._overlay_widgets:
            if widget is self._telemetry_panel:
                widget.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
                dock_layout.addWidget(widget, 1, Qt.AlignmentFlag.AlignTop)
            else:
                widget.setSizePolicy(
                    QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
                )
                dock_layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignTop)
        overlay_layout.addWidget(dock, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self._overlay_dock = dock
        self._dock_layout = dock_layout
        overlay_layout.addStretch(1)
        self._register_collapsible_panels()
        stack.addWidget(overlay)

        stack.setCurrentWidget(face_layer)
        overlay.raise_()

        self.setStyleSheet(
            """
            #robotScreen {
                background-color: #040914;
                border-radius: 20px;
                border: 1px solid rgba(68, 88, 128, 0.45);
            }
            #robotScreenFace > QWidget {
                border-radius: 20px;
            }
            #robotScreenOverlay {
                background: transparent;
            }
            """
        )

        self._update_overlay_geometry()

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        self._update_overlay_geometry()

    def _register_collapsible_panels(self) -> None:
        self._collapsible_panels = []
        for widget in self._overlay_widgets:
            signal = getattr(widget, "collapsedChanged", None)
            if signal is None:
                continue
            self._collapsible_panels.append(widget)
            signal.connect(partial(self._handle_panel_toggle, widget))
            signal.connect(lambda *_: self._update_overlay_geometry())

    def _handle_panel_toggle(self, source: QWidget, collapsed: bool) -> None:
        if collapsed:
            return
        for panel in self._collapsible_panels:
            if panel is source:
                continue
            collapse = getattr(panel, "collapse", None)
            is_collapsed = getattr(panel, "is_collapsed", None)
            if callable(collapse) and callable(is_collapsed) and not is_collapsed():
                collapse()
        self._update_overlay_geometry()

    def _update_overlay_geometry(self) -> None:
        if self._overlay_dock is None:
            return
        available_width = max(0, self.width() - 2 * self._overlay_margin)
        self._overlay_dock.setFixedWidth(available_width)
        if self._telemetry_panel is None:
            return
        collapsed_width = self._telemetry_panel.collapsed_width()
        if self._telemetry_panel.is_collapsed():
            width = collapsed_width
        else:
            reserved = 0
            if self._info_panel is not None:
                reserved = self._info_panel.collapsed_width()
            spacing = self._dock_layout.spacing() if self._dock_layout is not None else 0
            width = max(collapsed_width, available_width - reserved - spacing)
        self._set_panel_width(self._telemetry_panel, width)

    @staticmethod
    def _set_panel_width(panel: QWidget, width: int) -> None:
        width = max(0, int(width))
        panel.setMinimumWidth(width)
        panel.setMaximumWidth(width)
