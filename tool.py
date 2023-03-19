import numpy as np
import inochi2d.api as api
import inochi2d.inochi2d as inochi2d


class Tool:
    def __init__(self, window):
        self.window = window
        self.puppet = window.puppet
        self.camera = window.camera

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

    def draw(self):
        pass

class NodeTranslation(Tool):
    def __init__(self, window):
        super(NodeTranslation, self).__init__(window)
        self.drag = False

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

class DeformTranslation(Tool):
    def __init__(self, window):
        super(DeformTranslation, self).__init__(window)
        self.drag = False

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


class Deformer(Tool):
    def __init__(self, window):
        super(Deformer, self).__init__(window)
        self.drag = False
        self.selected = None
        self.vertices = None
        self.deformation = None
        self.target_node = None
        self.target_param = None

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
            self.vertices     = drawable.vertices
            self.deformation  = drawable.deformation
            self.transform    = drawable.transform

            local_pos = np.linalg.inv(self.transform) @ self.pos
            self.drag_start = local_pos
            distance = np.where(np.linalg.norm(self.vertices + self.deformation - local_pos[0:2], axis=1) < 6 / self.window.scale, 1, 0)
            if self.selected is None:
                self.selected = distance
            else:
                self.selected ^= distance
            

    def mouseMoveEvent(self, event):
        super(Deformer, self).mouseMoveEvent(event)
        if self.drag:
            self.pos[1] *= -1
            local_pos = np.linalg.inv(self.transform) @ self.pos
            diff_pos = local_pos - self.drag_start
            self.binding.value[self.keypoint[0], self.keypoint[1]] = (self.start_deform + np.append([self.selected], [self.selected], axis=0).T * np.repeat([diff_pos[0:2]], len(self.selected), axis=0)).astype(np.float32)
            self.binding.reinterpolate()

    def mouseReleaseEvent(self, event):
        super(Deformer, self).mouseReleaseEvent(event)
        if self.drag:
            self.drag = False

    def draw(self):
        if self.target_node and self.target_param and self.vertices is not None and self.deformation is not None and self.selected is not None:
            position = self.vertices + self.deformation
            new_position = np.zeros((len(self.vertices), 3), dtype=np.float32)
            new_position[:, 0:2] = position
            new_position = new_position[np.where(self.selected == 1)]
            inochi2d.dbg.set_buffer(new_position)
            inochi2d.dbg.points_size(6)
            inochi2d.dbg.draw_points(np.array([0, 1.0, 1.0, 1.0], dtype=np.float32), self.transform)
