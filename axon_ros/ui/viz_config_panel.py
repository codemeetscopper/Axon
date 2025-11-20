from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox, QGroupBox

class VizConfigPanel(QWidget):
    configChanged = Signal(float, float, float, float) # scale, rot_x, rot_y, rot_z
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Scale Control
        scale_group = QGroupBox("Model Scale")
        scale_layout = QHBoxLayout(scale_group)
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 5.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setValue(1.1)
        self.scale_spin.valueChanged.connect(self._emit_config)
        scale_layout.addWidget(QLabel("Scale:"))
        scale_layout.addWidget(self.scale_spin)
        layout.addWidget(scale_group)
        
        # Rotation Controls
        rot_group = QGroupBox("Mesh Orientation (Offsets)")
        rot_layout = QVBoxLayout(rot_group)
        
        # X Rotation
        x_layout = QHBoxLayout()
        self.rot_x_spin = QDoubleSpinBox()
        self.rot_x_spin.setRange(-360, 360)
        self.rot_x_spin.setSingleStep(180)
        self.rot_x_spin.setValue(0) # Default from previous fix
        self.rot_x_spin.valueChanged.connect(self._emit_config)
        x_layout.addWidget(QLabel("Rot X:"))
        x_layout.addWidget(self.rot_x_spin)
        rot_layout.addLayout(x_layout)
        
        # Y Rotation
        y_layout = QHBoxLayout()
        self.rot_y_spin = QDoubleSpinBox()
        self.rot_y_spin.setRange(-360, 360)
        self.rot_y_spin.setSingleStep(90)
        self.rot_y_spin.setValue(90) # Requested +90 Y
        self.rot_y_spin.valueChanged.connect(self._emit_config)
        y_layout.addWidget(QLabel("Rot Y:"))
        y_layout.addWidget(self.rot_y_spin)
        rot_layout.addLayout(y_layout)
        
        # Z Rotation
        z_layout = QHBoxLayout()
        self.rot_z_spin = QDoubleSpinBox()
        self.rot_z_spin.setRange(-360, 360)
        self.rot_z_spin.setSingleStep(90)
        self.rot_z_spin.setValue(-180) # Default from previous fix + requested +90? Let's start with 90 + 90 = 180?
        # User asked for +90 Z (previous) and then "rotate +90 deg in the axis perpendicular to the screen" (Z again?)
        # Let's set it to 180 as a guess, user can adjust.
        self.rot_z_spin.valueChanged.connect(self._emit_config)
        z_layout.addWidget(QLabel("Rot Z:"))
        z_layout.addWidget(self.rot_z_spin)
        rot_layout.addLayout(z_layout)
        
        layout.addWidget(rot_group)
        
    def _emit_config(self):
        self.configChanged.emit(
            self.scale_spin.value(),
            self.rot_y_spin.value(),
            self.rot_z_spin.value(),
            self.rot_x_spin.value()
        )
