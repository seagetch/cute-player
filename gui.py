import sys
sys.path.append("..")


from PySide2 import QtWidgets, QtOpenGL, QtGui, QtCore
from OpenGL import GL
import time
import ctypes
import inochi2d.api as api
import inochi2d.inochi2d as inochi2d
import math

WINDOW_WIDTH = 900
WINDOW_HEIGHT = 1300

class Inochi2DView(QtOpenGL.QGLWidget):
    def __init__(self, parent=None):
        format = QtOpenGL.QGLFormat()
        format.setVersion(3, 2)
        format.setSampleBuffers(True)
        super(Inochi2DView, self).__init__(format, parent)
        self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.tracker = None

        self.perf_time = None
        self.perf_counter = 0


    def initializeGL(self):

        @ctypes.CFUNCTYPE(ctypes.c_double)
        def curr_time():
            return time.time()

        inochi2d.init(curr_time)

        if self.onload:
            self.onload(self)
        timer = QtCore.QTimer()
        timer.timeout.connect(self.update)
        timer.start(1000/60)


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

        with inochi2d.Scene(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT) as scene:
            self.timer += 1
            if self.tracker is not None and len(self.tracker.latest_faces) > 0 and self.tracker.latest_faces[0] is not None:
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
                    list_item[0].setValue(nvs[0]*100)
                    if param.is_vec2:
                        list_item[1].setValue(nvs[1]*100)
                        
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
                value = bind_item.binding.get_value(ix, iy)
                bind_item.setText("%s: %s : %s"%(target_name, name, "%d pts"%len(value) if isinstance(value, list) else "%3.2f"%value))
        time_diff = time.time() - self.perf_time
        if time_diff > 1:
            print(self.perf_counter / time_diff)
            self.perf_time = time.time()
            self.perf_counter = 0
        self.update()

def run(tracker=None):
    app = QtWidgets.QApplication([])
    window = QtWidgets.QMainWindow()
    toplevel = QtWidgets.QWidget()
    hbox = QtWidgets.QHBoxLayout()
    vbox = QtWidgets.QVBoxLayout()

    hbox.addLayout(vbox)
    list_widget = QtWidgets.QListWidget(window)
    vbox.addWidget(list_widget)
    bind_list   = QtWidgets.QListWidget(window)
    vbox.addWidget(bind_list)

    vbox = QtWidgets.QVBoxLayout()
    hbox.addLayout(vbox)
    tree_widget = QtWidgets.QTreeWidget(window)
    vbox.addWidget(tree_widget)
    text_area = QtWidgets.QTextEdit()
    vbox.addWidget(text_area)

    def onload(self):
        self.puppet = inochi2d.Puppet.load("/home/seagetch/ドキュメント/Midori-exporttest-20230304-2.inp")
        self.active_param = None
        name = api.inPuppetGetName(self.puppet.handle)
        print(name)
        root = self.puppet.root()
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

        dump_node(root, None)
        tree_widget.itemClicked.connect(dump_json)
        list_widget.itemClicked.connect(param_selected)
        tree_widget.expandAll()


        params = self.puppet.parameters()
        self.params = {}
        for param in params:
            uuid = param.uuid()
            name = param.name()
            if param.is_vec2:
                x, y = param.get_value()
            else:
                x = param.get_value()
                y = 0
            list_item = QtWidgets.QListWidgetItem("%s"%(name))
            list_item.param = param
            progress_bars = [QtWidgets.QProgressBar(list_widget), QtWidgets.QProgressBar(list_widget)]
            min = param.min()
            max = param.max()
            for i, li in enumerate(progress_bars):
                li.setMinimum(int(min[i] * 100))
                li.setMaximum(int(max[i] * 100))
#                li.setFormat(name)
            list_widget.addItem(list_item)
            list_widget.setItemWidget(list_item, progress_bars[0])
            self.params[name] = (param, progress_bars)
        inochi2d.Viewport.set(WINDOW_WIDTH, WINDOW_HEIGHT)
        camera = inochi2d.Camera.get_current()
        camera.set_zoom(0.26)
        camera.set_position(0., 0.)

        self.timer = 0


    gl_widget = Inochi2DView()
    hbox.addWidget(gl_widget)
    gl_widget.onload = onload
    gl_widget.tracker = tracker

    toplevel.setLayout(hbox)
    window.setCentralWidget(toplevel)
    window.setWindowTitle("Cute Player")
    window.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)

    window.show()
    app.exec_()
    tracker.terminate = True

if __name__ == '__main__':
    run()