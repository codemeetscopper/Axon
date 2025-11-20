import sys
import os
import numpy as np
from stl import mesh
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QFileDialog)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *

# Add parent directory to path to import from robot_control
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from robot_control.remote_bridge import RemoteBridgeController, DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT
from robot_control.sensor_data import SensorSample

# Dummy classes to satisfy RemoteBridgeController dependencies
class DummyFaceWidget:
    def available_emotions(self):
        return ["neutral", "happy", "sad"]
    
    def set_emotion(self, emotion):
        pass
        
    def set_orientation(self, yaw=0, pitch=0, roll=0):
        pass

class DummyTelemetryPanel:
    def update_sample(self, sample):
        pass
        
    def set_streaming(self, streaming):
        pass

class RobotGLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.x_rot = 0
        self.y_rot = 0
        self.z_rot = 0
        self.mesh_data = None
        
        # Generate a default cube if no STL is loaded
        self.generate_default_cube()

    def generate_default_cube(self):
        # Create a simple cube mesh
        data = np.zeros(12, dtype=mesh.Mesh.dtype)
        cube = mesh.Mesh(data, remove_empty_areas=False)
        # Define vertices for a cube
        vertices = np.array([
            [-1, -1, -1],
            [+1, -1, -1],
            [+1, +1, -1],
            [-1, +1, -1],
            [-1, -1, +1],
            [+1, -1, +1],
            [+1, +1, +1],
            [-1, +1, +1],
        ])
        # Define 12 triangles (faces)
        indices = np.array([
            [0,3,1], [1,3,2], # Back face
            [0,4,7], [0,7,3], # Left face
            [4,5,6], [4,6,7], # Front face
            [5,1,2], [5,2,6], # Right face
            [2,3,6], [3,7,6], # Top face
            [0,1,5], [0,5,4]  # Bottom face
        ])
        
        for i, f in enumerate(indices):
            for j in range(3):
                cube.vectors[i][j] = vertices[f[j]]
        
        self.mesh_data = cube

    def load_stl(self, filename):
        try:
            self.mesh_data = mesh.Mesh.from_file(filename)
            self.update()
            return True
        except Exception as e:
            print(f"Error loading STL: {e}")
            return False

    def set_rotation(self, yaw, pitch, roll):
        # Map robot coordinates to OpenGL coordinates if necessary
        # Robot: Yaw (Z), Pitch (Y), Roll (X) usually
        self.z_rot = yaw
        self.y_rot = pitch
        self.x_rot = roll
        self.update()

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glClearColor(0.1, 0.1, 0.1, 1.0)
        
        # Light position
        glLightfv(GL_LIGHT0, GL_POSITION,  (0, 10, 10, 0))

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, w / h if h > 0 else 1, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        # Move camera back
        glTranslatef(0.0, 0.0, -10.0)
        
        # Apply rotations
        # Note: Order of rotation matters. 
        # Assuming standard aerospace sequence: Yaw -> Pitch -> Roll
        glRotatef(self.x_rot, 1, 0, 0) # Roll
        glRotatef(self.y_rot, 0, 1, 0) # Pitch
        glRotatef(self.z_rot, 0, 0, 1) # Yaw
        
        # Draw mesh
        if self.mesh_data is not None:
            glColor3f(0.0, 0.8, 1.0) # Cyan color
            glBegin(GL_TRIANGLES)
            for vector in self.mesh_data.vectors:
                # Calculate normal for flat shading
                v1 = vector[1] - vector[0]
                v2 = vector[2] - vector[0]
                normal = np.cross(v1, v2)
                norm_len = np.linalg.norm(normal)
                if norm_len > 0:
                    normal /= norm_len
                glNormal3fv(normal)
                
                glVertex3fv(vector[0])
                glVertex3fv(vector[1])
                glVertex3fv(vector[2])
            glEnd()

class RobotVizWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Robot 3D Telemetry Visualizer")
        self.resize(800, 600)
        
        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Top control bar
        control_layout = QHBoxLayout()
        
        self.host_input = QLineEdit(DEFAULT_BRIDGE_HOST)
        self.host_input.setPlaceholderText("Host IP")
        control_layout.addWidget(QLabel("Host:"))
        control_layout.addWidget(self.host_input)
        
        self.port_input = QLineEdit(str(DEFAULT_BRIDGE_PORT))
        self.port_input.setPlaceholderText("Port")
        control_layout.addWidget(QLabel("Port:"))
        control_layout.addWidget(self.port_input)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        control_layout.addWidget(self.connect_btn)
        
        self.load_stl_btn = QPushButton("Load STL")
        self.load_stl_btn.clicked.connect(self.load_stl_file)
        control_layout.addWidget(self.load_stl_btn)
        
        layout.addLayout(control_layout)
        
        # Status label
        self.status_label = QLabel("Disconnected")
        layout.addWidget(self.status_label)
        
        # 3D View
        self.gl_widget = RobotGLWidget()
        layout.addWidget(self.gl_widget)
        
        # Telemetry display
        self.telemetry_label = QLabel("Telemetry: Waiting...")
        layout.addWidget(self.telemetry_label)
        
        # Setup RemoteBridgeController
        self.dummy_face = DummyFaceWidget()
        self.dummy_panel = DummyTelemetryPanel()
        self.controller = RemoteBridgeController(self.dummy_face, self.dummy_panel)
        
        # Connect signals
        self.controller.connectionStateChanged.connect(self.on_connection_state_changed)
        self.controller.telemetryReceived.connect(self.on_telemetry_received)
        self.controller.errorOccurred.connect(self.on_error)

    @Slot()
    def toggle_connection(self):
        if self.controller.is_connected():
            self.controller.disconnect()
        else:
            host = self.host_input.text()
            try:
                port = int(self.port_input.text())
                self.controller.connect_to(host, port)
                self.status_label.setText(f"Connecting to {host}:{port}...")
            except ValueError:
                QMessageBox.warning(self, "Invalid Port", "Port must be a number.")

    @Slot()
    def load_stl_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Open STL File", "", "STL Files (*.stl)")
        if fname:
            if self.gl_widget.load_stl(fname):
                self.status_label.setText(f"Loaded {os.path.basename(fname)}")
            else:
                QMessageBox.critical(self, "Error", "Failed to load STL file.")

    @Slot(object)
    def on_connection_state_changed(self, state):
        # Convert enum to string for display
        state_str = str(state).split('.')[-1]
        self.status_label.setText(f"Status: {state_str}")
        
        if state == 3: # ConnectedState
            self.connect_btn.setText("Disconnect")
        else:
            self.connect_btn.setText("Connect")

    @Slot(SensorSample)
    def on_telemetry_received(self, sample: SensorSample):
        # Update text
        self.telemetry_label.setText(
            f"Yaw: {sample.yaw:.2f}, Pitch: {sample.pitch:.2f}, Roll: {sample.roll:.2f}"
        )
        
        # Update 3D model
        # Note: SensorSample has .yaw, .pitch, .roll properties
        # We might need to use calibrated values if raw ones are noisy or offset
        # sample.calibrated_yaw, etc.
        
        # Using raw values for now as per request "contains yaw, roll, pitch values"
        # But usually visualization wants the calibrated/oriented values.
        # Let's try calibrated first as it's likely what the user wants for "position"
        
        self.gl_widget.set_rotation(sample.calibrated_yaw, sample.calibrated_pitch, sample.calibrated_roll)

    @Slot(str)
    def on_error(self, error_msg):
        self.status_label.setText(f"Error: {error_msg}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RobotVizWindow()
    window.show()
    sys.exit(app.exec())
