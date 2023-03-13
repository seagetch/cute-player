import sys
sys.path.append("inochi2d-py")

from PySide2 import QtWidgets, QtOpenGL, QtGui, QtCore
from OpenGL import GL
import time
import ctypes
import inochi2d.api as api
import inochi2d.inochi2d as inochi2d
import threading

WINDOW_WIDTH = 1300
WINDOW_HEIGHT = 1200

class Inochi2DView(QtOpenGL.QGLWidget):
    def __init__(self, parent=None):
        format = QtOpenGL.QGLFormat()
        format.setVersion(3, 2)
        format.setSampleBuffers(True)
        super(Inochi2DView, self).__init__(format, parent)
        self.tracker = None

        self.perf_time = None
        self.perf_counter = 0
        self.drag = False

        self.initialized = False

    def initializeGL(self):
        @ctypes.CFUNCTYPE(ctypes.c_double)
        def curr_time():
            return time.perf_counter_ns()

        inochi2d.init(curr_time)

        if self.onload:
            self.onload(self)
#        timer = QtCore.QTimer()
#        timer.timeout.connect(self.update)
#        timer.start(1000/60)
        self.initialized = True
        inochi2d.Viewport.set(self.width(), self.height())

    def resizeGL(self, w, h):
        inochi2d.Viewport.set(self.width(), self.height())

    def mousePressEvent(self, event):
        self.drag = True
        self.drag_start = event.pos()
        self.drag_camera_pos = self.camera.get_position()

    def mouseMoveEvent(self, event):
        if self.drag:
            ascalev = 1 / self.scale if self.scale > 0 else 1
            pos = event.pos() - self.drag_start
            self.camera.set_position(self.drag_camera_pos[0] + pos.x() * ascalev, self.drag_camera_pos[1] + pos.y() * ascalev)
            self.update()

    def mouseReleaseEvent(self, event):
        self.drag = False

    def wheelEvent(self, event):
        delta = 1 + (event.angleDelta().y() / 180.0) * .3
        self.scale *= delta
        self.camera.set_zoom(self.scale)

    def paintGL(self):
        if self.perf_time is None:
            self.perf_time = time.time()
        self.perf_counter += 1
        try:
            # It seems inochi2d leaves some GL error, and OpenGL.GL see it as an error for successive command.
            GL.glClearColor(1.0, 1.0, 1.0, 1.0)
        except GL.GLError as e:
            pass
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        self.timer += 1
        if self.tracker is not None and not self.tracker.terminate and len(self.tracker.latest_faces) > 0 and self.tracker.latest_faces[0] is not None:
            face = self.tracker.latest_faces[0]
            for name, p_info in self.params.items():
                param, list_item = p_info
                vals = param.get_value()
                nvs = vals
                def dampen(vals, new_vals, r = 2):
                    return [v + (tv - v) / r for v, tv in zip(vals, new_vals)]
                if name == "Eye:: Left:: Blink":
                    nvs = dampen (vals, [1 - face.eye_blink[0], 0])
                elif name == "Eye:: Right:: Blink":
                    nvs = dampen(vals, [1 - face.eye_blink[1], 0])
                elif name == "Mouth:: Shape":
                    nvs = dampen(vals, [0.5, face.current_features["mouth_open"]])
                elif name == "Mouth:: Width":
                    nvs = dampen(vals, [face.current_features["mouth_wide"], 0])
                elif name == "Head:: Yaw-Pitch" or name == "Body:: Yaw-Pitch":
                    nvs = dampen(vals, [min(1, max(-1, -face.euler[1]/30)), min(1, max(-1, -(180 - face.euler[0])%360/30))])
                elif name == "Head:: Roll" or name == "Body:: Roll":
                    nvs = dampen(vals, [min(1, max(-1, (face.euler[2]-90)/30)), 0])
                if nvs[0] != vals[0] or nvs[1] != vals[0]:
                    param.set_value(*nvs)
#                    list_item.setText("%s, %f, %f"%(name, nx, ny))
                list_item.setValue(nvs)
                    
        with inochi2d.Scene(0, 0, self.width(), self.height()) as scene:
            self.puppet.update()
            self.puppet.draw()
    
        if self.active_param:
            kx, ky = self.active_param.get_value()
            ix, iy = self.active_param.find_closest_keypoint(kx, ky)
            for bind_item in self.bindings:
                binding = bind_item.binding
                name = binding.name()
                target = binding.node()
                target_name = target.name()
                if isinstance(bind_item.value, inochi2d.Deformation):
                    bind_item.value.pull(ix, iy)
                    value = bind_item.value
                else:
                    bind_item.value = bind_item.binding.get_value(ix, iy)
                    value = bind_item.value
                bind_item.setText("%s: %s : %s"%(target_name, name, "%d pts"%len(value.vertex_offsets) if isinstance(value, inochi2d.Deformation) else "%3.2f"%value))
        
        time_diff = time.time() - self.perf_time
        if time_diff > 1:
            self.statusbar.showMessage("%5.2f fps | %5.2f fps(OpenSeeFace)"%(self.perf_counter / time_diff, self.tracker.last_fps_counter))
            self.perf_time = time.time()
            self.perf_counter = 0
        self.update()

class ParameterView(QtWidgets.QWidget):
    def __init__(self, param, parent=None):
        super(ParameterView, self).__init__(parent)
        self.param = param
        self.setMinimumSize(120, 120 + 16 if self.param.is_vec2 else 16 + 16)
        self.min = self.param.min()
        self.max = self.param.max()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding
        )

        self.on_select = None
        self.on_update = None
        self.drag      = False

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        brush = QtGui.QBrush()
        brush.setColor(QtGui.QColor('#eeeeee'))
        brush.setStyle(QtCore.Qt.SolidPattern)

        rect = QtCore.QRect(2, 2, painter.device().width()-4, painter.device().height()-4)
        painter.fillRect(rect, brush)

        painter.setPen(QtGui.QColor('#a0a0a0'))
        rect = QtCore.QRect(8, 8 + 16, painter.device().width()-16, painter.device().height()-16-16)
        dev_w = painter.device().width() - 16
        dev_h = painter.device().height() - 16 - 16
        painter.drawRect(rect)

        painter.setPen(QtGui.QColor('black'))
        painter.drawText(8, 8 + 12, self.param.name())

        if self.param:
            value = self.param.get_value()

            radius = 4
            brush.setColor(QtGui.QColor("red"))
            painter.setBrush(brush)
            if self.param.is_vec2:
                x_ratio = (value[0] - self.min[0])/(self.max[0] - self.min[0])
                y_ratio = (value[1] - self.min[1])/(self.max[1] - self.min[1])
                center_x = 8 + dev_w * x_ratio
                center_y = 8 + 16 + dev_h * y_ratio
            else:
                x_ratio = (value[0] - self.min[0])/(self.max[0] - self.min[0])
                center_x = 8 + dev_w * x_ratio
                center_y = 8 + 16
            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)

    def setValue(self, value):
        self.update()

    def mousePressEvent(self, event):
        if self.on_select:
            self.on_select(self)
        if self._update_in_rect(event.pos()):
            self.drag = True
            return
        super(ParameterView, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._update_in_rect(event.pos()) or self.drag:
            return
        super(ParameterView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag:
            self.drag = False
        super(ParameterView, self).mouseReleaseEvent(event)

    def _update_in_rect(self, pos):
        wide_rect = QtCore.QRect(8-4, 8 + 16-4, self.width() - 16+8, self.height() - 16-16+8)
        rect = QtCore.QRect(8, 8 + 16, self.width() - 16, self.height() - 16-16)
        if wide_rect.contains(pos) or self.drag:
            pos = pos - rect.topLeft()
            pos_x = max(rect.left() - 8, min(pos.x(), rect.right() - 8))
            pos_y = max(rect.top() - 8 - 16, min(pos.y(), rect.bottom() - 8 - 16))
            pos_x = pos_x / rect.size().width()
            pos_y = ( pos_y / rect.size().height() ) if rect.size().height() > 0 else 0
            x = (self.max[0] - self.min[0]) * pos_x + self.min[0]
            y = (self.max[1] - self.min[1]) * pos_y + self.min[1]
            self.drag = True
            if self.on_update:
                self.on_update(self, x, y)
            else:
                self.param.set_value(x, y)
                self.update()
            return True
        return False


def run(tracker=None):
    app = QtWidgets.QApplication([])

    window = QtWidgets.QMainWindow()
    menubar = window.menuBar()
    fileMenu = menubar.addMenu("&File")
    statusbar = window.statusBar()
    dock_l = [QtWidgets.QDockWidget("L%d"%i, window) for i in range(4)]
    window.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock_l[0])
    window.splitDockWidget(dock_l[0], dock_l[2], QtCore.Qt.Horizontal);
    window.splitDockWidget(dock_l[0], dock_l[1], QtCore.Qt.Vertical);
    window.splitDockWidget(dock_l[2], dock_l[3], QtCore.Qt.Vertical);
    toolbar = window.addToolBar("Main")

#    list_widget = QtWidgets.QListWidget(dock_l[0])
    list_container = QtWidgets.QScrollArea(dock_l[0])
    list_widget = QtWidgets.QWidget()
    list_container.setWidget(list_widget)
    list_container.setWidgetResizable(True)
    dock_l[0].setWidget(list_container)
    bind_list   = QtWidgets.QListWidget(dock_l[1])
    dock_l[1].setWidget(bind_list)
    tree_widget = QtWidgets.QTreeWidget(dock_l[2])
    dock_l[2].setWidget(tree_widget)
    text_area = QtWidgets.QTextEdit(dock_l[3])
    dock_l[3].setWidget(text_area)

    def onload(self):
        self.puppet = inochi2d.Puppet.load("/home/seagetch/ドキュメント/Midori-exporttest-20230304-2.inp")
        self.active_param = None
        print("puppet:get_name")
        name = api.inPuppetGetName(self.puppet.handle)
        print(name)
        print("puppet:root")
        root = self.puppet.root()
        print("puppet:root:done")
        def dump_json(item, col):
            text_area.setPlainText(item.node.dumps())

        def dump_node(node, parent):
            name = node.name()
            type_id = node.type_id()
            tree_item = QtWidgets.QTreeWidgetItem(["%s: %s"%(type_id, name)])
            tree_item.node = node
            if parent is None:
                tree_widget.addTopLevelItem(tree_item)
            else:
                parent.addChild(tree_item)
            for c in node.children():
                dump_node(c, tree_item)

        def param_selected(item):
            bind_list.clear()
            self.active_param = item.param
            bindings = item.param.get_bindings()
            self.bindings = []
            kx, ky = self.active_param.get_value()
            ix, iy = self.active_param.find_closest_keypoint(kx, ky)
            for binding in bindings:
                name = binding.name()
                target = binding.node()
                target_name = target.name()
                bind_item = QtWidgets.QListWidgetItem("%s: %s"%(target_name, name))
                bind_list.addItem(bind_item)
                bind_item.binding = binding
                name = binding.name()
                target = binding.node()
                bind_item.setText("%s: %s"%(target_name, name))
                self.bindings.append(bind_item)
                bind_item.value = None

        dump_node(root, None)
        tree_widget.itemClicked.connect(dump_json)
        tree_widget.expandAll()


        print("puppet:parameters")
        params = self.puppet.parameters()
        self.params = {}
        vbox = QtWidgets.QVBoxLayout()
        list_widget.setLayout(vbox)
        for param in params:
            uuid = param.uuid()
            name = param.name()
            if param.is_vec2:
                x, y = param.get_value()
            else:
                x = param.get_value()
                y = 0
            list_item = ParameterView(param, list_widget)
            vbox.addWidget(list_item)
            self.params[name] = (param, list_item)
            list_item.on_select = param_selected

        self.scale = 0.26
        self.camera = inochi2d.Camera.get_current()
        self.camera.set_zoom(self.scale)
        self.camera.set_position(0., 0.)

        self.timer = 0

    gl_widget = Inochi2DView(window)
    gl_widget.statusbar = statusbar
    window.setCentralWidget(gl_widget)
    gl_widget.onload = onload
    gl_widget.tracker = tracker

    def toggle_tracking(self):
        if gl_widget.tracker.terminate:
            gl_widget.tracker.terminate = False
            threading.Thread(target=gl_widget.tracker.run).start()
        else:
            gl_widget.tracker.terminate = True

    toggle_track_action = QtWidgets.QAction("Track", window)
    toggle_track_action.setStatusTip("Enable/disable tracking")
    toggle_track_action.triggered.connect(toggle_tracking)
    toolbar.addAction(toggle_track_action)


    window.setWindowTitle("Cute Player")
    window.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)

    window.show()
    app.exec_()
    tracker.terminate = True

if __name__ == '__main__':
    run()