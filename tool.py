import numpy as np
import inochi2d.api as api
import inochi2d.inochi2d as inochi2d
from PySide2 import QtCore

class Tool:
    def __init__(self, window):
        self.window = window
        self.puppet = window.puppet
        self.camera = window.camera

    def init(self):
        pass

    def mousePressEvent(self, event):
        self.pos = np.array([event.pos().x(), event.pos().y(), 0, 1], dtype=np.float32)
        self.matrix = self.camera.screen_to_global
        self.pos = self.matrix @ self.pos

    def mouseMoveEvent(self, event):
        self.pos = np.array([event.pos().x(), event.pos().y(), 0, 1], dtype=np.float32)
        self.pos = self.matrix @ self.pos

    def mouseReleaseEvent(self, event):
        self.pos = np.array([event.pos().x(), event.pos().y(), 0, 1], dtype=np.float32)
        self.pos = self.matrix @ self.pos

    def draw(self, node):
        pass


class NodeTool(Tool):
    def draw(self, node):
        # Bounds
        bounds_x, bounds_y, bounds_z, bounds_w = node.combined_bounds
        position = np.array([[bounds_x, bounds_y, 0], [bounds_z, bounds_y, 0], 
                                [bounds_z, bounds_y, 0], [bounds_z, bounds_w, 0], 
                                [bounds_z, bounds_w, 0], [bounds_x, bounds_w, 0],
                                [bounds_x, bounds_w, 0], [bounds_x, bounds_y, 0]], dtype=np.float32)
        inochi2d.dbg.set_buffer(position)
        inochi2d.dbg.line_width(3)
        inochi2d.dbg.draw_lines(np.array([1, 0.6, 0, 1.0], dtype=np.float32), None)

        # Points
        try:
            drawable = inochi2d.Drawable(node)
            position = drawable.vertices + drawable.deformation
            new_position = np.zeros((len(position), 3), dtype=np.float32)
            new_position[:, 0:2] = position
            dynamic_matrix = drawable.dynamic_matrix
            inochi2d.dbg.set_buffer(new_position)
            inochi2d.dbg.points_size(5)
            inochi2d.dbg.draw_points(np.array([0, 0, 0, 1.0], dtype=np.float32), dynamic_matrix)
            inochi2d.dbg.points_size(3)
            inochi2d.dbg.draw_points(np.array([1, 0.6, 0, 1.0], dtype=np.float32), dynamic_matrix)
        except Exception:
            pass


class NodeTranslation(NodeTool):
    def __init__(self, window):
        super(NodeTranslation, self).__init__(window)
        self.drag = False

    def init(self):
        self.window.setCursor(QtCore.Qt.SizeAllCursor)

    def mousePressEvent(self, event):
        super(NodeTranslation, self).mousePressEvent(event)
        self.pos[1] *= -1
        self.drag_start = self.pos
        self.drag = True
        target = self.window.active_node
        if target:
            self.start_value = target.translation

    def mouseMoveEvent(self, event):
        super(NodeTranslation, self).mouseMoveEvent(event)
        if self.drag:
            target = self.window.active_node
            if target:
                self.pos[1] *= -1
                diff_pos = self.pos - self.drag_start
                target.translation = self.start_value + diff_pos[0:3]

    def mouseReleaseEvent(self, event):
        super(NodeTranslation, self).mouseReleaseEvent(event)
        self.drag = False


class NodeRotation(NodeTool):
    def __init__(self, window):
        super(NodeRotation, self).__init__(window)
        self.drag = False

    def init(self):
        self.window.setCursor(QtCore.Qt.CrossCursor)

    def mousePressEvent(self, event):
        super(NodeRotation, self).mousePressEvent(event)
        self.pos[1] *= -1
        target_node  = self.window.active_node
        if target_node:
            self.drag = True
            self.transform    = target_node.transform
            local_pos = np.linalg.inv(self.transform) @ self.pos
            unit_pos = local_pos[0:2] / np.linalg.norm(local_pos[0:2])
            self.start_angle = np.arctan2(unit_pos[1], unit_pos[0])
            self.start_value = np.array(target_node.rotation)

    def mouseMoveEvent(self, event):
        super(NodeRotation, self).mouseMoveEvent(event)
        if self.drag:
            target_node = self.window.active_node
            self.pos[1] *= -1
            local_pos = np.linalg.inv(self.transform) @ self.pos
            unit_pos = local_pos[0:2] / np.linalg.norm(local_pos[0:2])
            cur_angle   = np.arctan2(unit_pos[1], unit_pos[0])
            diff_angle  = cur_angle - self.start_angle
            target_node.rotation = self.start_value + np.array([0, 0, (diff_angle + np.pi)%(2*np.pi) - np.pi])

    def mouseReleaseEvent(self, event):
        super(NodeRotation, self).mouseReleaseEvent(event)
        if self.drag:
            self.drag = False


class NodeScaling(NodeTool):
    def __init__(self, window):
        super(NodeScaling, self).__init__(window)
        self.drag = False

    def init(self):
        self.window.setCursor(QtCore.Qt.SizeBDiagCursor)

    def mousePressEvent(self, event):
        super(NodeScaling, self).mousePressEvent(event)
        target = self.window.active_node
        if target:
            self.drag = True
            self.transform = target.transform
            local_pos = self.transform @ self.pos
            self.drag_start = local_pos
            self.start_value = target.scale

    def mouseMoveEvent(self, event):
        super(NodeScaling, self).mouseMoveEvent(event)
        if self.drag:
            target = self.window.active_node
            if target:
                local_pos = self.transform @ self.pos
                scale = np.abs(np.nan_to_num(local_pos[0:2] / self.drag_start[0:2], nan = 1.0))
                target.scale = self.start_value * scale

    def mouseReleaseEvent(self, event):
        super(NodeScaling, self).mouseReleaseEvent(event)
        self.drag = False


class DeformationTool(Tool):
    def draw(self, node):
        # Bounds
        bounds_x, bounds_y, bounds_z, bounds_w = node.combined_bounds
        position = np.array([[bounds_x, bounds_y, 0], [bounds_z, bounds_y, 0], 
                                [bounds_z, bounds_y, 0], [bounds_z, bounds_w, 0], 
                                [bounds_z, bounds_w, 0], [bounds_x, bounds_w, 0],
                                [bounds_x, bounds_w, 0], [bounds_x, bounds_y, 0]], dtype=np.float32)
        inochi2d.dbg.set_buffer(position)
        inochi2d.dbg.line_width(3)
        if self.window.active_param:
            inochi2d.dbg.draw_lines(np.array([0, 0.6, 1.0, 1.0], dtype=np.float32), None)
        else:
            inochi2d.dbg.draw_lines(np.array([0.5, 0.5, 0.5, 1.0], dtype=np.float32), None)

        # Points
        try:
            drawable = inochi2d.Drawable(node)
            position = drawable.vertices + drawable.deformation
            new_position = np.zeros((len(position), 3), dtype=np.float32)
            new_position[:, 0:2] = position
            self.dynamic_matrix = drawable.dynamic_matrix
            inochi2d.dbg.set_buffer(new_position)
            inochi2d.dbg.points_size(5)
            inochi2d.dbg.draw_points(np.array([0, 0, 0, 1.0], dtype=np.float32), self.dynamic_matrix)
            inochi2d.dbg.points_size(3)
            if self.window.active_param:
                inochi2d.dbg.draw_points(np.array([0, 0.6, 1, 1.0], dtype=np.float32), self.dynamic_matrix)
            else:
                inochi2d.dbg.draw_points(np.array([0.5, 0.5, 0.5, 1.0], dtype=np.float32), self.dynamic_matrix)

        except Exception:
            pass
        self.draw_position = new_position


class DeformTranslation(DeformationTool):
    def __init__(self, window):
        super(DeformTranslation, self).__init__(window)
        self.drag = False

    def init(self):
        self.window.setCursor(QtCore.Qt.SizeAllCursor)

    def mousePressEvent(self, event):
        super(DeformTranslation, self).mousePressEvent(event)
        self.pos[1] *= -1
        self.drag_start = self.pos
        target_node  = self.window.active_node
        target_param = self.window.active_param
        if target_node and target_param:
            self.drag = True
            self.keypoint = target_param.find_closest_keypoint()
            self.binding_x = target_param.get_or_add_binding(target_node, "transform.t.x")
            self.binding_y = target_param.get_or_add_binding(target_node, "transform.t.y")
            self.start_value_x = self.binding_x.value[self.keypoint[0], self.keypoint[1]]
            self.start_value_y = self.binding_y.value[self.keypoint[0], self.keypoint[1]]

    def mouseMoveEvent(self, event):
        super(DeformTranslation, self).mouseMoveEvent(event)
        if self.drag:
            self.pos[1] *= -1
            diff_pos = self.pos - self.drag_start
            self.binding_x.value[self.keypoint[0], self.keypoint[1]] = self.start_value_x + diff_pos[0]
            self.binding_y.value[self.keypoint[0], self.keypoint[1]] = self.start_value_y + diff_pos[1]
            self.binding_x.reinterpolate()
            self.binding_y.reinterpolate()

    def mouseReleaseEvent(self, event):
        super(DeformTranslation, self).mouseReleaseEvent(event)
        if self.drag:
            self.drag = False


class DeformRotation(DeformationTool):
    def __init__(self, window):
        super(DeformRotation, self).__init__(window)
        self.drag = False

    def init(self):
        self.window.setCursor(QtCore.Qt.CrossCursor)

    def mousePressEvent(self, event):
        super(DeformRotation, self).mousePressEvent(event)
        self.pos[1] *= -1
        target_node  = self.window.active_node
        target_param = self.window.active_param
        if target_node and target_param:
            self.drag = True
            self.transform    = target_node.transform
            local_pos = np.linalg.inv(self.transform) @ self.pos
            unit_pos = local_pos[0:2] / np.linalg.norm(local_pos[0:2])
            self.start_angle = np.arctan2(unit_pos[1], unit_pos[0])
            self.keypoint = target_param.find_closest_keypoint()
            self.binding_z = target_param.get_or_add_binding(target_node, "transform.r.z")
            self.start_value_z = self.binding_z.value[self.keypoint[0], self.keypoint[1]]

    def mouseMoveEvent(self, event):
        super(DeformRotation, self).mouseMoveEvent(event)
        if self.drag:
            self.pos[1] *= -1
            local_pos = np.linalg.inv(self.transform) @ self.pos
            unit_pos = local_pos[0:2] / np.linalg.norm(local_pos[0:2])
            cur_angle   = np.arctan2(unit_pos[1], unit_pos[0])
            diff_angle  = cur_angle - self.start_angle
            self.binding_z.value[self.keypoint[0], self.keypoint[1]] = (self.start_value_z + diff_angle + np.pi)%(2*np.pi) - np.pi
            self.binding_z.reinterpolate()

    def mouseReleaseEvent(self, event):
        super(DeformRotation, self).mouseReleaseEvent(event)
        if self.drag:
            self.drag = False


class DeformScaling(DeformationTool):
    def __init__(self, window):
        super(DeformScaling, self).__init__(window)
        self.drag = False

    def init(self):
        self.window.setCursor(QtCore.Qt.SizeBDiagCursor)

    def mousePressEvent(self, event):
        super(DeformScaling, self).mousePressEvent(event)
        target_node = self.window.active_node
        target_param = self.window.active_param
        if target_node and target_param:
            self.drag = True
            self.transform = target_node.transform
            local_pos = self.transform @ self.pos
            self.drag_start = local_pos
            self.keypoint = target_param.find_closest_keypoint()
            self.binding_x = target_param.get_or_add_binding(target_node, "transform.s.x")
            self.binding_y = target_param.get_or_add_binding(target_node, "transform.s.y")
            self.start_value_x = self.binding_x.value[self.keypoint[0], self.keypoint[1]]
            self.start_value_y = self.binding_y.value[self.keypoint[0], self.keypoint[1]]

    def mouseMoveEvent(self, event):
        super(DeformScaling, self).mouseMoveEvent(event)
        if self.drag:
            local_pos = self.transform @ self.pos
            scale = np.abs(np.nan_to_num(local_pos[0:2] / self.drag_start[0:2], nan = 1.0))
            self.binding_x.value[self.keypoint[0], self.keypoint[1]] = scale[0] * self.start_value_x
            self.binding_y.value[self.keypoint[0], self.keypoint[1]] = scale[1] * self.start_value_y
            self.binding_x.reinterpolate()
            self.binding_y.reinterpolate()

    def mouseReleaseEvent(self, event):
        super(DeformScaling, self).mouseReleaseEvent(event)
        self.drag = False


class Deformer(DeformationTool):
    RADIUS = 8

    def __init__(self, window):
        super(Deformer, self).__init__(window)
        self.drag = False
        self.selected = None
        self.vertices = None
        self.deformation = None
        self.target_node = None
        self.target_param = None
        self.selecting    = None
        self.transform = None

    def init(self):
        self.window.setCursor(QtCore.Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        super(Deformer, self).mousePressEvent(event)
        self.pos[1] *= -1
        target_node  = self.window.active_node
        target_param = self.window.active_param
        if target_node and target_param:
            if target_node != self.target_node:
                self.selected = None
            if target_param != self.target_param:
                self.keypoint = None
            self.target_node = target_node
            self.target_param = target_param
            self.drag = True
            self.keypoint     = target_param.find_closest_keypoint()
            self.binding      = target_param.get_or_add_binding(target_node, "deform")
            self.binding.reinterpolate()
            self.start_deform = np.copy(self.binding.value[self.keypoint[0], self.keypoint[1]])
            drawable = inochi2d.Drawable(target_node)
            self.vertices     = drawable.vertices + drawable.deformation
            self.transform    = drawable.dynamic_matrix

            local_pos = np.linalg.inv(self.transform) @ self.pos
            self.drag_start = local_pos
            selected = np.where(np.linalg.norm(self.vertices - local_pos[0:2], axis=1) < self.RADIUS / self.window.scale)
            selected_map = np.zeros((len(self.vertices),), dtype=np.int)
            if len(selected[0]) > 0:
                selected_map[selected] = 1
                if self.selected is None or np.sum(self.selected * selected_map) == 0:
                    self.selected = selected_map
                else:
                    self.selected = self.selected | selected_map
            else:
                self.selecting = selected_map
            

    def mouseMoveEvent(self, event):
        super(Deformer, self).mouseMoveEvent(event)
        if self.transform is not None:
            self.pos[1] *= -1
            local_pos = np.linalg.inv(self.transform) @ self.pos
        if self.selecting is not None:
            rect = np.array([self.drag_start[0:2], local_pos[0:2]])
            self.selecting = (np.min(rect, axis=0) <= self.vertices) & (self.vertices <= np.max(rect, axis=0))
            self.selecting = self.selecting[:, 0] & self.selecting[:, 1]
            self.rect = rect
        elif self.drag:
            diff_pos = local_pos - self.drag_start
            selected = np.append([self.selected], [self.selected], axis=0).T
            pos      = np.repeat([diff_pos[0:2]], len(self.selected), axis=0)
            self.binding.value[self.keypoint[0], self.keypoint[1]] = (self.start_deform + selected * pos).astype(np.float32)
            self.binding.reinterpolate()

    def mouseReleaseEvent(self, event):
        super(Deformer, self).mouseReleaseEvent(event)
        if self.selecting is not None:
            self.selected = self.selecting
            self.selecting = None
        if self.drag:
            self.drag     = False
            drawable = inochi2d.Drawable(self.target_node)
            self.vertices = drawable.vertices + drawable.deformation

    def draw(self, node):
        super(Deformer, self).draw(node)
        if self.target_node and self.target_node.uuid == node.uuid:
            dynamic_matrix = self.dynamic_matrix
            if self.selected is not None and len(self.selected) > 0:
                # Selected point
                selected = self.draw_position[np.where(self.selected == 1)]
                inochi2d.dbg.set_buffer(selected)
                inochi2d.dbg.points_size(self.RADIUS)
                inochi2d.dbg.draw_points(np.array([0, 0, 0, 1.0], dtype=np.float32), dynamic_matrix)
                inochi2d.dbg.points_size(self.RADIUS - 2)
                inochi2d.dbg.draw_points(np.array([0, 1, 1, 1.0], dtype=np.float32), dynamic_matrix)
            if self.selecting is not None and len(self.selecting) > 0:
                # Selection floating
                selecting = self.draw_position[np.where(self.selecting)]
                inochi2d.dbg.set_buffer(selecting)
                inochi2d.dbg.draw_points(np.array([0, 1.0, 0, 1.0], dtype=np.float32), dynamic_matrix)