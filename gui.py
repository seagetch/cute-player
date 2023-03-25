import sys
sys.path.append("inochi2d-py")

from PySide2 import QtWidgets, QtOpenGL, QtGui, QtCore
from OpenGL import GL
import time
import numpy as np
import inochi2d.api as api
import inochi2d.inochi2d as inochi2d
import threading
import json
import cv2
import qtawesome as qta

from tool import *

#from qt_material import apply_stylesheet

WINDOW_WIDTH = 1300
WINDOW_HEIGHT = 1200

class Inochi2DView(QtOpenGL.QGLWidget):
    def __init__(self, parent=None):
        format = QtOpenGL.QGLFormat()
        format.setVersion(3, 2)
        format.setSampleBuffers(True)
        super(Inochi2DView, self).__init__(format, parent)
        self.tracker = None

        self.puppet = None
        self.params = []
        self.perf_time = None
        self.perf_counter = 0
        self.drag = False
        self.on_update_tracking = None

        self.initialized = False
        self.tool = None
        self.active_node = None

    def initializeGL(self):
        inochi2d.init()

        if self.onload:
            self.onload(self)
        self.initialized = True
        inochi2d.Viewport.set(self.width(), self.height())

    def resizeGL(self, w, h):
        inochi2d.Viewport.set(self.width(), self.height())

    def mousePressEvent(self, event):
        if event.button() is QtCore.Qt.MouseButton.MidButton:
            self.drag = True
            self.drag_start = event.pos()
            self.drag_camera_pos = self.camera.position
            self.matrix = self.camera.screen_to_global
        elif self.tool:
            self.tool.mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag:
            pos = np.array([event.pos().x(), event.pos().y(), 0, 1])
            relpos=self.matrix @ pos

            ascalev = 1 / self.scale if self.scale > 0 else 1
            pos = event.pos() - self.drag_start
            self.camera.position = (self.drag_camera_pos[0] + pos.x() * ascalev, self.drag_camera_pos[1] + pos.y() * ascalev)
            self.update()
        elif self.tool:
            self.tool.mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() is QtCore.Qt.MouseButton.MidButton:
            self.drag = False
        elif self.tool:
                self.tool.mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.tool:
            self.tool.mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        delta = 1 + (event.angleDelta().y() / 180.0) * .3
        self.scale *= delta
        self.camera.zoom = self.scale

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
                vals = param.value
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
                    param.value = nvs
#                    list_item.setText("%s, %f, %f"%(name, nx, ny))
                list_item.setValue(nvs)
        if self.puppet:
            with inochi2d.Scene(0, 0, self.width(), self.height()) as scene:
                self.puppet.update()
                api.inUpdate()
                self.puppet.draw()

            if self.active_node and self.tool:
                drawable = inochi2d.Drawable(self.active_node)
                drawable.draw_mesh_lines()
                self.tool.draw(self.active_node)
    
        if self.on_update_tracking:
            self.on_update_tracking(self)
        
        time_diff = time.time() - self.perf_time
        if time_diff > 1:
            self.statusbar.showMessage("%5.2f fps | %5.2f fps(OpenSeeFace)"%(self.perf_counter / time_diff, self.tracker.last_fps_counter))
            self.perf_time = time.time()
            self.perf_counter = 0
        self.update()

class ParameterView(QtWidgets.QWidget):
    def __init__(self, param, parent=None):
        super(ParameterView, self).__init__(parent)
        self.param_list = parent
        self.param = param
        self.setMinimumSize(120, 120 + 16 if self.param.is_vec2 else 16 + 16)
        self.min = self.param.min
        self.max = self.param.max
        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding
        )

        self.on_select = None
        self.on_update = None
        self.drag      = False
        self.active    = False

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        if self.active:
            rect = QtCore.QRect(0, 0, painter.device().width(), painter.device().height())
            painter.fillRect(rect, self.palette().highlight())

        brush = QtGui.QBrush()
        brush.setColor(QtGui.QColor('#eeeeee'))
        brush.setStyle(QtCore.Qt.SolidPattern)

        rect = QtCore.QRect(2, 2, painter.device().width()-4, painter.device().height()-4)
        painter.fillRect(rect, brush)

        painter.setPen(QtGui.QColor('#a0a0a0'))
        rect = QtCore.QRect(8, 8 + 16, painter.device().width()-16, painter.device().height()-16-16)
        dev_w = painter.device().width() - 16
        dev_h = painter.device().height() - 16 - 16
        if self.param_list.active:
            brush.setColor(QtGui.QColor('#f8f8f8'))
            painter.fillRect(rect, brush)
        painter.drawRect(rect)

        painter.setPen(QtGui.QColor('black'))
        painter.drawText(8, 8 + 12, self.param.name)

        if self.param:
            value = self.param.value

            radius = 4
            if self.param_list.active:
                brush.setColor(QtGui.QColor("red"))
            else:
                brush.setColor(QtGui.QColor("#808080"))
            painter.setBrush(brush)
            if self.param.is_vec2:
                x_ratio = (value[0] - self.min[0])/(self.max[0] - self.min[0])
                y_ratio = 1 - (value[1] - self.min[1])/(self.max[1] - self.min[1])
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
        if not self.param_list.active:
            return
        if self.on_select:
            self.on_select(self)
        if self._update_in_rect(event.pos()):
            self.drag = True
            return
        super(ParameterView, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.param_list.active:
            return
        if self._update_in_rect(event.pos()) or self.drag:
            return
        super(ParameterView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.param_list.active:
            return
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
            pos_y = 1 - pos_y
            x = (self.max[0] - self.min[0]) * pos_x + self.min[0]
            y = (self.max[1] - self.min[1]) * pos_y + self.min[1]
            self.drag = True
            if self.on_update:
                self.on_update(self, x, y)
            else:
                self.param.value = (x, y)
                self.update()
            return True
        return False


def run(tracker=None):
    ICON_SIZE=16

    app = QtWidgets.QApplication([])

#    apply_stylesheet(app, 'light_blue.xml')

    window = QtWidgets.QMainWindow()
    menubar = window.menuBar()
    file_menu = menubar.addMenu("&File")

    open_action = QtWidgets.QAction("&Open...", window)
    file_menu.addAction(open_action)

    def load_model(_):
        self = gl_widget
#        model_name = "/home/seagetch/ドキュメント/gimp-tan-20220923-1.5.8-serde2.inx"
#        model_name = "/home/seagetch/ドキュメント/Midori-serdetest-20230315.inx"
#        model_name = "/home/seagetch/ドキュメント/Midori-exporttest-20230304-2.inp"
        model_name = QtWidgets.QFileDialog.getOpenFileName(
            None,
            "Open Model",
            "",
            "Inochi2D models (*.inp *.inx)",
            "",
            QtWidgets.QFileDialog.Options()
        )[0]
        print(model_name)
        self.puppet = inochi2d.Puppet.load(model_name)
        self.puppet.enable_drivers = True
        self.active_param = None
        name = api.inPuppetGetName(self.puppet.handle)
        print(name)
        root = self.puppet.root
        def dump_json(item, col):
            self.active_node = item.node
            text_area.setPlainText(json.dumps(item.node.dumps(False), indent=4, ensure_ascii=False))

        def dump_node(node, parent):
            name = node.name
            type_id = node.type_id
            tree_item = QtWidgets.QTreeWidgetItem(["%s: %s"%(type_id, name)])
            tree_item.node = node
            node_prop = node.dumps(recursive=False)
            if "textures" in node_prop:
                texture_id = node_prop["textures"][0]
                if texture_id <= 65535:
                    texture = self.puppet.get_texture_from_id(texture_id)
                    w,h = texture.size
                    channels = texture.channels
                    img = texture.data
                    img = img.reshape([h, w, channels])
                    scale = min(ICON_SIZE/w, ICON_SIZE/h)
                    icon = cv2.resize(img, None, None, scale, scale)
                    qimg = QtGui.QImage(icon.data, icon.shape[1], icon.shape[0], icon.strides[0], QtGui.QImage.Format_RGBA8888)
                    qpixmap = QtGui.QPixmap(qimg)
                    qicon = QtGui.QIcon(qpixmap)
                    tree_item.setIcon(0, qicon)
                    tree_item.setText(0, "%s"%(name))
            elif type_id == "Node":
                qicon = qta.icon("mdi.folder")
                tree_item.setIcon(0, qicon)
                tree_item.setText(0, "%s"%(name))
            elif type_id == "MeshGroup":
                qicon = qta.icon("mdi.border-all")
                tree_item.setIcon(0, qicon)
                tree_item.setText(0, "%s"%(name))
            elif type_id == "Composite":
                qicon = qta.icon("mdi.camera")
                tree_item.setIcon(0, qicon)
                tree_item.setText(0, "%s"%(name))
            elif type_id == "SimplePhysics":
                qicon = qta.icon("mdi.slope-downhill")
                tree_item.setIcon(0, qicon)
                tree_item.setText(0, "%s"%(name))

            if parent is None:
                tree_widget.addTopLevelItem(tree_item)
            else:
                parent.addChild(tree_item)
            for c in node.children():
                dump_node(c, tree_item)
        tree_widget.clear()
        dump_node(root, None)
        tree_widget.itemClicked.connect(dump_json)
        tree_widget.expandAll()
        tree_widget.setStyleSheet("QTreeWidget::item { padding: 0; margin: 0}")

        # Parameter View

        def param_selected(item):
            if param_list.active_widget != item:
                prev_active = param_list.active_widget
                if prev_active:
                    prev_active.active = False
                    prev_active.update()
                param_list.active_widget = item
                item.active = True
                param_list.update()
            bind_list.clear()
            self.active_param = item.param
            bindings = item.param.bindings
            self.bindings = []
            kx, ky = self.active_param.value
            ix, iy = self.active_param.find_closest_keypoint(kx, ky)
            for binding in bindings:
                name = binding.name
                target = binding.node
                target_name = target.name
                bind_item = QtWidgets.QListWidgetItem("%s: %s"%(target_name, name))
                bind_list.addItem(bind_item)
                bind_item.binding = binding
                name = binding.name
                target = binding.node
                bind_item.setText("%s: %s"%(target_name, name))
                self.bindings.append(bind_item)
                bind_item.value = None

        params = self.puppet.parameters
        self.params = {}
        vbox = QtWidgets.QVBoxLayout()
        param_list.setLayout(vbox)
        param_list.active = False
        for param in params:
            uuid = param.uuid
            name = param.name
            if param.is_vec2:
                x, y = param.value
            else:
                x = param.value
                y = 0
            list_item = ParameterView(param, param_list)
            vbox.addWidget(list_item)
            self.params[name] = (param, list_item)
            list_item.on_select = param_selected

        transform_action.setChecked(True)
        transform_action.activate(QtWidgets.QAction.Trigger)

    open_action.triggered.connect(load_model)


    statusbar = window.statusBar()
    toolbar = QtWidgets.QToolBar("Main", window) #window.addToolBar("Main")
    v_toolbar = QtWidgets.QToolBar("Tool", window)

    list_container = QtWidgets.QScrollArea(window)
    param_list = QtWidgets.QWidget()
    param_list.active_widget = None
    param_list.active = False
    list_container.setWidget(param_list)
    list_container.setWidgetResizable(True)
    
    bind_list   = QtWidgets.QListWidget(window)
    
    tree_widget = QtWidgets.QTreeWidget(window)
    tree_widget.setIconSize(QtCore.QSize(ICON_SIZE, ICON_SIZE))
    tree_widget.setHeaderHidden(True)

    text_area = QtWidgets.QTextEdit(window)
    docked_widgets = {
        "Parameters": list_container,
        "Parameter Bindings": bind_list,
        "Node Tree View": tree_widget,
        "Node Inspection": text_area
    }

    dock_l = [QtWidgets.QDockWidget(name, window) for name in docked_widgets.keys()]
    for i, widget in enumerate(docked_widgets.values()):
        dock_l[i].setWidget(widget)
    window.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock_l[0])
    window.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock_l[1])
    window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock_l[2])
    window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock_l[3])
#    window.splitDockWidget(dock_l[0], dock_l[2], QtCore.Qt.Horizontal);
#    window.splitDockWidget(dock_l[0], dock_l[1], QtCore.Qt.Vertical);
#    window.splitDockWidget(dock_l[2], dock_l[3], QtCore.Qt.Vertical);

    gl_widget = Inochi2DView(window)
    gl_widget.statusbar = statusbar

    def onload(self):
        inochi2d.dbg.draw_mesh_outlines      = True
        inochi2d.dbg.draw_mesh_vertex_points = True
        inochi2d.dbg.draw_mesh_orientations  = True
        inochi2d.Drawable.set_update_bounds(True)
        self.scale = 0.26
        self.camera = inochi2d.Camera.get_current()
        self.camera.zoom = self.scale
        self.camera.position = (0., 0.)

        self.timer = 0

    # Layout of Main Area
    gl_widget.onload = onload
    gl_widget.tracker = tracker

    main_container = QtWidgets.QWidget(window)
    sub_container = QtWidgets.QWidget(window)
    
    main_vbox = QtWidgets.QVBoxLayout()
    main_vbox.setContentsMargins(0,0,0,0)
    main_vbox.setSpacing(0)
    sub_container.setLayout(main_vbox)
    main_vbox.addWidget(toolbar)

    main_hbox = QtWidgets.QHBoxLayout()
    main_hbox.setContentsMargins(0,0,0,0)
    main_hbox.setSpacing(0)
    main_container.setLayout(main_hbox)
    main_hbox.addWidget(v_toolbar)

    main_hbox.addWidget(sub_container)
    v_toolbar.setOrientation(QtCore.Qt.Vertical)
    v_toolbar.setStyleSheet("QToolBar {background: rgb(128, 128, 128)}")

    main_vbox.addWidget(gl_widget)


    # Set up Vertical Toolbar
    window.tool_actions = []
    tool_group = QtWidgets.QActionGroup(window)

    mode_group = QtWidgets.QActionGroup(window)
    parts_layout_action = QtWidgets.QAction(qta.icon("mdi.human", color="white"), "Parts Layout", mode_group, checkable=True)
    v_toolbar.addAction(parts_layout_action)
    toolbar.option_widgets = []

    def select_handler(action):
        def on_select(isChecked):
            if isChecked:
                gl_widget.tool = action
                gl_widget.setCursor(QtCore.Qt.ArrowCursor)
                if gl_widget.tool:
                    gl_widget.tool.init()
                    for widget in toolbar.option_widgets:
                        toolbar.removeAction(widget)
                    gl_widget.tool.show_toolbar(toolbar, spacer2)
        return on_select
    def on_toggle_parts_layout(isChecked):
        if isChecked:
            tool_id = -1
            if gl_widget.tool:
                tool_id = gl_widget.tool.id
            gl_widget.tool = None
            for action in window.tool_actions:
                v_toolbar.removeAction(action)
            window.tool_actions = []
            param_list.active = False
            param_list.update()
            for param in gl_widget.puppet.parameters:
                param.reset()

            color = QtGui.QColor(int(1 * 255), int(0.7 * 255), 0)
            toolbar.setStyleSheet("""QToolBar, QToolBar QWidget {background: rgb(%d, %d, %d); padding: 0 }"""%(color.red(), color.green(), color.blue()))
 
            action = QtWidgets.QAction(qta.icon("fa.arrows", color=color), "Translate", tool_group, checkable=True)
            tool   = NodeTranslation(gl_widget)
            tool.id = len(window.tool_actions)
            action.toggled.connect(select_handler(tool))
            v_toolbar.addAction(action)
            window.tool_actions.append(action)

            action = QtWidgets.QAction(qta.icon("fa.rotate-left", color=color), "Rotate", tool_group, checkable=True)
            tool   = NodeRotation(gl_widget)
            tool.id = len(window.tool_actions)
            action.toggled.connect(select_handler(tool))
            v_toolbar.addAction(action)
            window.tool_actions.append(action)

            action = QtWidgets.QAction(qta.icon("mdi.arrow-top-right-bottom-left-bold", color=color), "Scale", tool_group, checkable=True)
            tool   = NodeScaling(gl_widget)
            tool.id = len(window.tool_actions)
            action.toggled.connect(select_handler(tool))
            v_toolbar.addAction(action)
            window.tool_actions.append(action)

            action = QtWidgets.QAction(qta.icon("mdi.graphql", color=color), "Edit Vertices", tool_group, checkable=True)
            tool   = NodeMeshEditor(gl_widget)
            tool.id = len(window.tool_actions)
            action.toggled.connect(select_handler(tool))
            v_toolbar.addAction(action)
            window.tool_actions.append(action)
            if tool_id >= 0 and tool_id < len(window.tool_actions) and window.tool_actions[tool_id]:
                window.tool_actions[tool_id].setChecked(True)
                window.tool_actions[tool_id].activate(QtWidgets.QAction.Trigger)

    parts_layout_action.toggled.connect(on_toggle_parts_layout)

    transform_action = QtWidgets.QAction(qta.icon("msc.settings", color="white"), "Transformation", mode_group, checkable=True)
    v_toolbar.addAction(transform_action)

    def on_toggle_transform(isChecked):
        if isChecked:
            tool_id = -1
            if gl_widget.tool:
                tool_id = gl_widget.tool.id
            gl_widget.tool = None
            for action in window.tool_actions:
                v_toolbar.removeAction(action)
            window.tool_actions = []

            param_list.active = True
            param_list.update()

            color = QtGui.QColor(0, int(0.8 * 255), int(1 * 255))
            toolbar.setStyleSheet("""QToolBar, QToolBar QWidget {background: rgb(%d, %d, %d); padding: 0 }"""%(color.red(), color.green(), color.blue()))
 
            action = QtWidgets.QAction(qta.icon("fa.arrows", color=color), "Translate", tool_group, checkable=True)
            tool   = DeformTranslation(gl_widget)
            tool.id = len(window.tool_actions)
            action.toggled.connect(select_handler(tool))
            v_toolbar.addAction(action)
            window.tool_actions.append(action)

            action = QtWidgets.QAction(qta.icon("fa.rotate-left", color=color), "Rotate", tool_group, checkable=True)
            tool   = DeformRotation(gl_widget)
            tool.id = len(window.tool_actions)
            action.toggled.connect(select_handler(tool))
            v_toolbar.addAction(action)
            window.tool_actions.append(action)

            action = QtWidgets.QAction(qta.icon("mdi.arrow-top-right-bottom-left-bold", color=color), "Scale", tool_group, checkable=True)
            tool   = DeformScaling(gl_widget)
            tool.id = len(window.tool_actions)
            action.toggled.connect(select_handler(tool))
            v_toolbar.addAction(action)
            window.tool_actions.append(action)

            action = QtWidgets.QAction(qta.icon("mdi.graphql", color=color), "Edit Vertices", tool_group, checkable=True)
            tool   = Deformer(gl_widget)
            tool.id = len(window.tool_actions)
            action.toggled.connect(select_handler(tool))
            v_toolbar.addAction(action)
            window.tool_actions.append(action)

            action = QtWidgets.QAction(qta.icon("mdi.border-all", color=color), "Warp Transform", tool_group, checkable=True)
            v_toolbar.addAction(action)
            tool   = None
#            tool.id = len(window.tool_actions)
            action.toggled.connect(select_handler(tool))
            window.tool_actions.append(action)
            if tool_id >= 0 and tool_id < len(window.tool_actions) and window.tool_actions[tool_id]:
                window.tool_actions[tool_id].setChecked(True)
                window.tool_actions[tool_id].activate(QtWidgets.QAction.Trigger)

    transform_action.toggled.connect(on_toggle_transform)

    action = QtWidgets.QAction(qta.icon("mdi.animation-play", color="white"), "Animation Timeline", mode_group, checkable=True)
    v_toolbar.addAction(action)

    def on_toggle_animation(isChecked):
        if isChecked:
            for action in window.tool_actions:
                v_toolbar.removeAction(action)

    action.toggled.connect(on_toggle_animation)
    
    v_toolbar.addSeparator()
    _spacer = QtWidgets.QWidget(v_toolbar)
    _spacer.setMinimumSize(10, 32)
    v_toolbar.addWidget(_spacer)

    window.setCentralWidget(main_container)

    def on_update_tracking(self):
        if self.active_param:
            kx, ky = self.active_param.value()
            ix, iy = self.active_param.find_closest_keypoint(kx, ky)
            for bind_item in self.bindings:
                binding = bind_item.binding
                name = binding.name
                target = binding.node()
                target_name = target.name
                if isinstance(bind_item.value, inochi2d.Deformation):
                    bind_item.value.pull(ix, iy)
                    value = bind_item.value
                else:
                    bind_item.value = bind_item.binding.value(ix, iy)
                    value = bind_item.value
                bind_item.setText("%s: %s : %s"%(target_name, name, "%d pts"%len(value) if isinstance(value, np.ndarray) else "%3.2f"%value))

#    gl_widget.on_update_tracking = on_update_tracking

    view_group = QtWidgets.QActionGroup(window)
    puppet_view_action    = QtWidgets.QAction(qta.icon("mdi.shape"), "Puppet edit view", view_group, checkable=True)
    toolbar.addAction(puppet_view_action)
    zoom_node_view_action = QtWidgets.QAction(qta.icon("mdi.magnify"), "Node edit view", view_group, checkable=True)
    toolbar.addAction(zoom_node_view_action)

    def toggle_tracking(self):
        if gl_widget.tracker.terminate:
            gl_widget.tracker.terminate = False
            threading.Thread(target=gl_widget.tracker.run).start()
        else:
            gl_widget.tracker.terminate = True

    spacer1 = QtWidgets.QWidget(window)
    spacer1.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
    spacer1 = toolbar.addWidget(spacer1)
    spacer2 = QtWidgets.QWidget(window)
    spacer2.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
    spacer2 = toolbar.addWidget(spacer2)

    toggle_track_action = QtWidgets.QAction(qta.icon("mdi.motion-sensor"), "Enable/disable tracking", window, checkable=True)
    toggle_track_action.toggled.connect(toggle_tracking)
    toolbar.addAction(toggle_track_action)


    window.setWindowTitle("Cute Player")
    window.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)

    window.show()
    app.exec_()
    tracker.terminate = True

if __name__ == '__main__':
    run()