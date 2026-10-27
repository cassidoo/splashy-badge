# Runs on the badge (via tools/capture_gif.py): stages a pool, drops a heavy
# Mona, and prints every frame as base64 RGB565 rows.
import binascii

FRAMES = 72
namespace = {"__name__": "__main__"}


def dump():
    print("FRAME_BEGIN", screen.width, screen.height, screen.stride)
    for y in range(screen.height):
        print(binascii.b2a_base64(screen.raw[y * screen.stride:(y + 1) * screen.stride]).decode().strip())


def scene(update):
    pool = namespace["pool"]
    renderer = namespace["renderer"]
    namespace["setup"] = None
    tilt = (0.1, -0.05)
    pool.color_index = 0
    pool.tilt_x, pool.tilt_z = tilt
    pool.view_x, pool.view_z = 0.03, -0.03
    pool.level = pool.target_level = -0.08
    for kind, weight in ((0, 0.45), (1, 0.5), (2, 0.55), (3, 0.6)):
        pool.add(kind, weight)
    for _ in range(240):
        pool.step(1 / 30, *tilt)
    del pool.drops[:]
    renderer.level_until = 0
    renderer.last_level = pool.target_level
    pool.serial = 1
    pool.add(3, 1.45)
    for _ in range(FRAMES):
        pool.step(1 / 30, *tilt)
        badge.clear()
        renderer.draw(pool)
        dump()
    print("GIF_DONE")


namespace["run"] = scene
exec(open("/system/apps/splashy_badge/__init__.py").read(), namespace)
