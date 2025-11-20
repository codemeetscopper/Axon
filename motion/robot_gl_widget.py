import numpy as np
from stl import mesh
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Slot, QThread, Signal, QObject, Qt
from PySide6.QtGui import QPainter, QColor, QFont
from OpenGL.GL import *
from OpenGL.GLU import *
from robot_control.sensor_data import SensorSample

class StlLoader(QObject):
    finished = Signal(object, object, float) # mesh_data, center_offset, auto_scale
    
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        
    def load(self):
        try:
            mesh_data = mesh.Mesh.from_file(self.filename)
            
            # Calculate bounds in thread
            all_points = mesh_data.vectors.reshape(-1, 3)
            min_bounds = all_points.min(axis=0)
            max_bounds = all_points.max(axis=0)
            center_offset = (min_bounds + max_bounds) / 2.0
            
            max_dim = np.max(max_bounds - min_bounds)
            if max_dim > 0:
                auto_scale = 10.0 / max_dim
            else:
                auto_scale = 1.0
                
            self.finished.emit(mesh_data, center_offset, auto_scale)
        except Exception as e:
            print(f"Error loading STL: {e}")
            self.finished.emit(None, None, 1.0)

class RobotGLWidget(QOpenGLWidget):
    def __init__(self, parent=None, stl_path=None, scale=1.0):
        super().__init__(parent)
        self.x_rot = 0
        self.y_rot = 0
        self.z_rot = 0
        self.mesh_data = None
        self.display_list = None
        self.scale = scale
        self.stl_path = stl_path
        self.loader_thread = None
        self.center_offset = np.array([0.0, 0.0, 0.0])
        self.auto_scale = 1.0
        self.is_loading = False
        self.load_error = None
        
        # Mesh Orientation Offsets (Configurable)
        self.mesh_rot_x = 180
        self.mesh_rot_y = 90
        self.mesh_rot_z = 180
        
        if stl_path:
            self.start_loading(stl_path)
        else:
            self.generate_default_cube()

    # ... (keep existing methods)

    def set_mesh_transform(self, scale, rot_x, rot_y, rot_z):
        self.scale = scale
        self.mesh_rot_x = rot_x
        self.mesh_rot_y = rot_y
        self.mesh_rot_z = rot_z
        self.update()

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        # Move camera back a bit more to see everything
        glTranslatef(0.0, 0.0, -20.0)
        
        # Draw axes at origin (fixed in world space)
        self.draw_axes()
        
        # Apply rotations (Telemetry)
        glRotatef(self.x_rot, 1, 0, 0) # Roll
        glRotatef(self.y_rot, 0, 1, 0) # Pitch
        glRotatef(self.z_rot, 0, 0, 1) # Yaw
        
        # Apply scaling (user scale * auto scale)
        final_scale = self.scale * self.auto_scale
        glScalef(final_scale, final_scale, final_scale)
        
        # Apply Mesh Orientation Offsets (Configurable)
        glRotatef(self.mesh_rot_x, 1, 0, 0)
        glRotatef(self.mesh_rot_y, 0, 1, 0)
        glRotatef(self.mesh_rot_z, 0, 0, 1)
        
        # Center the mesh
        glTranslatef(-self.center_offset[0], -self.center_offset[1], -self.center_offset[2])
        
        # Draw mesh
        if self.display_list:
            glCallList(self.display_list)
        elif self.mesh_data is not None:
            # Fallback if display list not ready
            glColor3f(0.0, 0.8, 1.0)
            glBegin(GL_TRIANGLES)
            for vector in self.mesh_data.vectors:
                glNormal3fv(np.cross(vector[1]-vector[0], vector[2]-vector[0]))
                glVertex3fv(vector[0])
                glVertex3fv(vector[1])
                glVertex3fv(vector[2])
            glEnd()
            
        # Overlay Status Text
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self.is_loading:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 16))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Loading 3D Model...")
        elif self.load_error:
            painter.setPen(QColor(255, 50, 50))
            painter.setFont(QFont("Arial", 14))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self.load_error}")
        
        painter.end()

    def start_loading(self, filename):
        self.is_loading = True
        self.load_error = None
        self.loader_thread = QThread()
        self.loader = StlLoader(filename)
        self.loader.moveToThread(self.loader_thread)
        self.loader_thread.started.connect(self.loader.load)
        self.loader.finished.connect(self.on_stl_loaded)
        self.loader.finished.connect(self.loader_thread.quit)
        self.loader.finished.connect(self.loader.deleteLater)
        self.loader_thread.finished.connect(self.loader_thread.deleteLater)
        self.loader_thread.start()
        self.update()

    def on_stl_loaded(self, mesh_data, center_offset, auto_scale):
        self.is_loading = False
        if mesh_data is not None:
            self.mesh_data = mesh_data
            self.center_offset = center_offset
            self.auto_scale = auto_scale
            self.create_display_list()
        else:
            self.load_error = "Failed to load STL"
            print("Error: Mesh data is None")
        self.update()

    def create_display_list(self):
        self.makeCurrent()
        self.display_list = glGenLists(1)
        glNewList(self.display_list, GL_COMPILE)
        
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
            
        glEndList()

    def generate_default_cube(self):
        # Create a simple cube mesh
        data = np.zeros(12, dtype=mesh.Mesh.dtype)
        cube = mesh.Mesh(data, remove_empty_areas=False)
        vertices = np.array([
            [-1, -1, -1], [+1, -1, -1], [+1, +1, -1], [-1, +1, -1],
            [-1, -1, +1], [+1, -1, +1], [+1, +1, +1], [-1, +1, +1],
        ])
        indices = np.array([
            [0,3,1], [1,3,2], [0,4,7], [0,7,3], [4,5,6], [4,6,7],
            [5,1,2], [5,2,6], [2,3,6], [3,7,6], [0,1,5], [0,5,4]
        ])
        for i, f in enumerate(indices):
            for j in range(3):
                cube.vectors[i][j] = vertices[f[j]]
        self.mesh_data = cube
        # Simple bounds for cube
        self.center_offset = np.array([0.0, 0.0, 0.0])
        self.auto_scale = 1.0

    def set_rotation(self, yaw, pitch, roll):
        self.z_rot = yaw
        self.y_rot = pitch
        self.x_rot = roll
        self.update()

    @Slot(SensorSample)
    def set_orientation_from_sample(self, sample: SensorSample):
        self.set_rotation(sample.calibrated_yaw, sample.calibrated_pitch, sample.calibrated_roll)

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_NORMALIZE)
        glClearColor(0.1, 0.1, 0.1, 1.0)
        glLightfv(GL_LIGHT0, GL_POSITION,  (0, 10, 10, 0))
        
        if self.mesh_data is not None and self.display_list is None:
            self.create_display_list()

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, w / h if h > 0 else 1, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

    def draw_axes(self):
        glDisable(GL_LIGHTING)
        glLineWidth(3.0) # Thicker lines
        glBegin(GL_LINES)
        
        # X Axis (Red)
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(10.0, 0.0, 0.0) # Longer
        
        # Y Axis (Green)
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 10.0, 0.0)
        
        # Z Axis (Blue)
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 10.0)
        
        glEnd()
        glLineWidth(1.0) # Reset
        glEnable(GL_LIGHTING)

    def set_mesh_transform(self, scale, rot_x, rot_y, rot_z):
        self.scale = scale
        self.mesh_rot_x = rot_x
        self.mesh_rot_y = rot_y
        self.mesh_rot_z = rot_z
        self.update()

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        # Move camera back a bit more to see everything
        glTranslatef(0.0, 0.0, -20.0)
        
        # Draw axes at origin (fixed in world space)
        self.draw_axes()
        
        # Apply rotations (Telemetry)
        glRotatef(self.x_rot, 1, 0, 0) # Roll
        glRotatef(self.y_rot, 0, 1, 0) # Pitch
        glRotatef(self.z_rot, 0, 0, 1) # Yaw
        
        # Apply scaling (user scale * auto scale)
        final_scale = self.scale * self.auto_scale
        glScalef(final_scale, final_scale, final_scale)
        
        # Apply Mesh Orientation Offsets (Configurable)
        glRotatef(self.mesh_rot_x, 1, 0, 0)
        glRotatef(self.mesh_rot_y, 0, 1, 0)
        glRotatef(self.mesh_rot_z, 0, 0, 1)
        
        # Center the mesh
        glTranslatef(-self.center_offset[0], -self.center_offset[1], -self.center_offset[2])
        
        # Draw mesh
        if self.display_list:
            glCallList(self.display_list)
        elif self.mesh_data is not None:
            # Fallback if display list not ready
            glColor3f(0.0, 0.8, 1.0)
            glBegin(GL_TRIANGLES)
            for vector in self.mesh_data.vectors:
                glNormal3fv(np.cross(vector[1]-vector[0], vector[2]-vector[0]))
                glVertex3fv(vector[0])
                glVertex3fv(vector[1])
                glVertex3fv(vector[2])
            glEnd()
            
        # Overlay Status Text
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self.is_loading:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 16))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Loading 3D Model...")
        elif self.load_error:
            painter.setPen(QColor(255, 50, 50))
            painter.setFont(QFont("Arial", 14))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self.load_error}")
        
        painter.end()
