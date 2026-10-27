import math
import struct

from physics import HALF_X, HALF_Z, TOP

# The low-poly Mona the home screen already uses.
MODEL = "/system/apps/menu/mona_menu.p3d"
SCALE = 0.098
# Model-space height that floats at the object's position (just below the neck).
ANCHOR_Y = -1.45
EYE_DISTANCE = 2 * HALF_Z / 0.65
# Each Mona is cached as a small sprite; the anchor sits at (SPRITE_X, SPRITE_Y).
SPRITE_W, SPRITE_H = 40, 44
SPRITE_X, SPRITE_Y = 20, 24
# Re-render at most this many changed Monas per frame; the rest are blitted.
REFRESH_BUDGET = 2
REFRESH_MIN = 0.05
NEW = 99.0
# Sprites are captured from a magenta-keyed RGB565 screen patch.
KEY_RGB565 = 0xF81F
OPAQUE = -16777216  # 0xFF000000 as a signed machine word.

try:
    from sprite_kernel import capture
except (ImportError, NameError, SyntaxError):
    capture = None


def read_parts(path):
    """Read a P3DM/P3D2 model into (name, rgb, positions, normals, indices, colors)."""
    parts = []
    with open(path, "rb") as handle:
        magic, count = struct.unpack("<4sI", handle.read(8))
        if magic == b"P3DM":
            records = [struct.unpack("<16sIIIIII", handle.read(40)) + (0,)
                       for _ in range(count)]
        elif magic == b"P3D2":
            records = [struct.unpack("<16sIIIIIII", handle.read(44)) for _ in range(count)]
        else:
            raise ValueError("not a P3DM or P3D2 model")
        for name, rgb, verts, tris, pos, nrm, idx, col in records:
            blocks = []
            for offset, size in ((pos, verts * 12), (nrm, verts * 12), (idx, tris * 6),
                                 (col, verts * 4 if col else 0)):
                data = None
                if size:
                    data = bytearray(size)
                    handle.seek(offset)
                    handle.readinto(data)
                blocks.append(data)
            parts.append((name.rstrip(b"\0").decode(), rgb, verts, tris) + tuple(blocks))
    return parts


class MonaDrawer:
    """Draws glossy Mona models with pico3d, matching the tank's off-axis camera."""

    def __init__(self, pico3d, screen, color, path=MODEL, image=None, vec2=None):
        self.pico3d = pico3d
        self.screen = screen
        # Without image support every Mona is rendered straight to the screen.
        if capture is None or screen.stride != screen.width * 2:
            image = None
        self.image, self.vec2 = image, vec2
        self.key = color.rgb(255, 0, 255)
        self.sprites = {}
        self.spare = []
        self.eye = (0.0, 0.0)
        pico3d.engine.cores(2)
        self.surface = pico3d.surface(screen)
        self.parts = []
        vertices = triangles = 0
        white = color.rgb(255, 255, 255)
        for name, rgb, verts, tris, pos, nrm, idx, colors in read_parts(path):
            mesh = pico3d.mesh(positions=pos, normals=nrm, indices=idx, colors=colors,
                               quantise=True)
            material = pico3d.material(
                color=color.rgb((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255),
                shading=pico3d.material.GOURAUD, specular=white, shininess=24)
            self.parts.append((name, mesh, material))
            vertices += verts
            triangles += tris
        self.scene_args = (max(vertices * 2, triangles * 3), triangles * 2)
        self.scene = pico3d.scene(self.surface, meshes=len(self.parts),
                                  vertices=self.scene_args[0],
                                  triangles=self.scene_args[1])
        self.light = pico3d.light(color=color.rgb(120, 125, 130),
                                  ambient=color.rgb(205, 205, 212),
                                  direction=pico3d.vec3(-0.45, 0.8, 0.55))
        fov = math.degrees(2 * math.atan(TOP / EYE_DISTANCE))
        self.projection = pico3d.mat4.perspective(fov, HALF_X / TOP, 0.3, 4.5)
        self.camera = None
        self.view = None

    def begin(self, offset_x, offset_y, half_w, half_h, monas=(), project=None):
        """Aim the camera so the front face still fills the screen, then refresh
        stale sprites. Call before the frame is painted: refreshes use the screen."""
        pico3d = self.pico3d
        self.surface.clear_depth()
        eye_x = offset_x / half_w * HALF_X
        eye_y = -offset_y / half_h * TOP
        self.eye = (eye_x, eye_y)
        camera = (round(eye_x, 4), round(eye_y, 4))
        if camera != self.camera:
            self.camera = camera
            look = pico3d.mat4.look_at(pico3d.vec3(eye_x, eye_y, HALF_Z + EYE_DISTANCE),
                                       pico3d.vec3(eye_x, eye_y, 0),
                                       pico3d.vec3(0, 1, 0))
            # Shifting clip space keeps the front plane pinned to the screen corners.
            self.view = (pico3d.mat4().translate(eye_x / HALF_X, eye_y / TOP, 0)
                         * self.projection * look)

        if self.image is not None and project is not None:
            self.plan(monas)
            for obj in monas:
                sprite = self.sprites.get(id(obj))
                if sprite is not None and sprite[2]:
                    self.refresh(sprite, obj, *project(obj[0], obj[1], obj[2]))

    def plan(self, monas):
        """Pick which cached Mona sprites are stale enough to re-render this frame."""
        eye_x, eye_y = self.eye
        sprites, due = {}, []
        for obj in monas:
            key = id(obj)
            sprite = self.sprites.pop(key, None)
            if sprite is None:
                sprite = self.spare.pop() if self.spare else self.new_sprite()
                if sprite is None:
                    self.image = None
                    return
                sprite[1] = None
            sprites[key] = sprite
            sprite[2] = False
            pose = sprite[1]
            if pose is None:
                score = NEW
            else:
                score = (abs(obj[8] - pose[0]) + abs(obj[9] - pose[1])
                         + abs(obj[10] - pose[2]) + abs(obj[2] - pose[3]) * 2
                         + abs(obj[1] - pose[4]) * 0.3
                         + (abs(eye_x - pose[5]) + abs(eye_y - pose[6])) * 3)
            if score > REFRESH_MIN:
                due.append((score, key))
        # Sprites of removed Monas are kept for reuse.
        self.spare.extend(self.sprites.values())
        self.sprites = sprites
        due.sort(reverse=True)
        for n, (score, key) in enumerate(due):
            if n < REFRESH_BUDGET or score >= NEW:
                sprites[key][2] = True

    def new_sprite(self):
        try:
            # Image, pose it was rendered at, and whether it is due a refresh.
            return [self.image(SPRITE_W, SPRITE_H), None, False]
        except (MemoryError, ValueError, TypeError, OSError):
            return None

    def refresh(self, sprite, obj, x, y):
        """Render Mona onto a keyed screen patch and capture it into her sprite."""
        screen = self.screen
        left = int(x + 0.5) - SPRITE_X
        top = int(y + 0.5) - SPRITE_Y
        screen.pen = self.key
        screen.rectangle(left, top, SPRITE_W, SPRITE_H)
        self.surface.clear_depth()
        self.render(self.surface, self.scene, self.model(obj), self.view)
        capture(screen.raw, screen.stride // 2, left, top, sprite[0].raw, SPRITE_W, SPRITE_H,
                screen.width, screen.height, KEY_RGB565, OPAQUE)
        sprite[1] = (obj[8], obj[9], obj[10], obj[2], obj[1]) + self.eye
        # Patches clipped by the screen edge are retaken once Mona moves.
        sprite[2] = False
        if left < 0 or top < 0 or left + SPRITE_W > screen.width or top + SPRITE_H > screen.height:
            sprite[1] = (NEW,) + sprite[1][1:]

    def model(self, obj):
        return (self.pico3d.mat4().translate(obj[0], obj[1], obj[2])
                .rotate_y(math.degrees(obj[8]))
                .rotate_x(math.degrees(obj[9]))
                .rotate_z(math.degrees(obj[10]))
                .scale(SCALE)
                .translate(0, -ANCHOR_Y, 0))

    def render(self, surface, scene, model, view):
        scene.reset()
        for _, mesh, material in self.parts:
            scene.add(mesh, model, view, material, self.light)
        return surface.draw(scene)

    def draw(self, obj, x=0.0, y=0.0):
        """Draw Mona whose anchor projects to screen pixel (x, y)."""
        sprite = self.sprites.get(id(obj)) if self.image is not None else None
        if sprite is None or sprite[1] is None:
            self.surface.clear_depth()
            return self.render(self.surface, self.scene, self.model(obj), self.view)
        self.screen.blit(sprite[0], self.vec2(int(x + 0.5) - SPRITE_X, int(y + 0.5) - SPRITE_Y))
