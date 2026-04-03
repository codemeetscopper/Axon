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
from axon_ui.chat_bubble_overlay import ChatBubbleOverlay

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

        # Convert overlays to tuple
        if isinstance(overlays, Sequence):
            self._overlay_widgets = tuple(overlays)
        else:
            self._overlay_widgets = (overlays,)

        self._face = face
        self._fixed_size = fixed_size
        self._overlay_margin = 16

        # Find special panels
        self._telemetry_panel = next(
            (w for w in self._overlay_widgets if isinstance(w, TelemetryPanel)),
            None,
        )
        self._info_panel = next(
            (w for w in self._overlay_widgets if isinstance(w, InfoPanel)),
            None,
        )

        # Internal state
        self._overlay_dock: QWidget | None = None
        self._dock_layout: QHBoxLayout | None = None
        self._collapsible_panels: list[QWidget] = []

        self._build_ui()

    # ----------------------------------------------------------------------
    # UI BUILD
    # ----------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setObjectName("robotScreen")

        # Fixed or expanding size
        if self._fixed_size is not None:
            if isinstance(self._fixed_size, QSize):
                size = self._fixed_size
            else:
                w, h = self._fixed_size
                size = QSize(int(w), int(h))
            self.setFixedSize(size)
        else:
            self.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )

        self.setAttribute(Qt.WA_StyledBackground, True)

        # ------------------------------------
        # STACKED VIEW LAYER (CORRECT WAY)
        # ------------------------------------
        stack = QStackedLayout()
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setStackingMode(QStackedLayout.StackAll)
        self.setLayout(stack)

        # --- FACE LAYER ---
        face_layer = QFrame(self)
        face_layer.setObjectName("robotScreenFace")

        face_layout = QVBoxLayout(face_layer)
        face_layout.setContentsMargins(0, 0, 0, 0)
        face_layout.setSpacing(0)

        self._face.setParent(face_layer)  # safe
        self._face.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        face_layout.addWidget(self._face)

        stack.addWidget(face_layer)

        # --- OVERLAY LAYER ---
        overlay = QWidget(self)
        overlay.setObjectName("robotScreenOverlay")

        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(
            self._overlay_margin, self._overlay_margin,
            self._overlay_margin, self._overlay_margin
        )
        overlay_layout.setSpacing(0)

        # -----------------------
        # PROPER RIGHT-ALIGNED DOCK
        # -----------------------
        dock = QWidget(overlay)
        dock_layout = QHBoxLayout(dock)
        dock_layout.setContentsMargins(0, 0, 0, 0)
        dock_layout.setSpacing(10)

        # LEFT-side stretch forces widgets to the RIGHT
        dock_layout.addStretch(1)

        # Add widgets in correct order
        for widget in self._overlay_widgets:
            if widget is self._telemetry_panel:
                # Telemetry panel grows horizontally
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                dock_layout.addWidget(widget)
            else:
                # Other panels stay minimal
                widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                dock_layout.addWidget(widget)

        # Top alignment handled by the vertical layout
        overlay_layout.addWidget(dock, 0, Qt.AlignTop)
        overlay_layout.addStretch(1)

        self._overlay_dock = dock
        self._dock_layout = dock_layout

        self._register_collapsible_panels()

        stack.addWidget(overlay)

        # --- CHAT BUBBLE LAYER ---
        self._chat_overlay = ChatBubbleOverlay(self)
        stack.addWidget(self._chat_overlay)
        self._chat_overlay.raise_()

        overlay.raise_()

        # ------------------------------------
        # STYLES
        # ------------------------------------
        self.setStyleSheet("""
            #robotScreen {
                background-color: #040914;
                border-radius: 20px;
                border: 0px solid rgba(68, 88, 128, 0.45);
            }
            #robotScreenFace > QWidget {
                border-radius: 20px;
            }
            #robotScreenOverlay {
                background: transparent;
            }
        """)

        self._update_overlay_geometry()

    # ----------------------------------------------------------------------
    # EVENTS
    # ----------------------------------------------------------------------
    @property
    def chat_overlay(self) -> ChatBubbleOverlay:
        return self._chat_overlay

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_overlay_geometry()

    # ----------------------------------------------------------------------
    # COLLAPSIBLE PANELS
    # ----------------------------------------------------------------------
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

        # Collapse all others
        for panel in self._collapsible_panels:
            if panel is source:
                continue

            collapse_fn = getattr(panel, "collapse", None)
            is_collapsed_fn = getattr(panel, "is_collapsed", None)

            if callable(collapse_fn) and callable(is_collapsed_fn) and not is_collapsed_fn():
                collapse_fn()

        self._update_overlay_geometry()

    # ----------------------------------------------------------------------
    # GEOMETRY MANAGEMENT
    # ----------------------------------------------------------------------
    def _update_overlay_geometry(self) -> None:
        if not self._overlay_dock:
            return

        available_width = max(0, self.width() - 2 * self._overlay_margin)
        self._overlay_dock.setFixedWidth(available_width)

        if not self._telemetry_panel:
            return

        collapsed_width = self._telemetry_panel.collapsed_width()

        if self._telemetry_panel.is_collapsed():
            width = collapsed_width
        else:
            reserved = 0
            if self._info_panel:
                reserved = self._info_panel.collapsed_width()
            spacing = self._dock_layout.spacing() if self._dock_layout else 0

            width = max(collapsed_width, available_width - reserved - spacing)

        self._set_panel_width(self._telemetry_panel, width)

    @staticmethod
    def _set_panel_width(panel: QWidget, width: int) -> None:
        width = max(0, int(width))
        panel.setMinimumWidth(width)
        panel.setMaximumWidth(width)
