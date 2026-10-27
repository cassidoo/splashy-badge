import binascii
import time

frames = []
namespace = {"__name__": "__main__"}


def bounded_run(update):
    from physics import BOTTOM, REST
    pool = namespace["pool"]
    renderer = namespace["renderer"]
    # A badge with no saved labels opens setup first; skip it for the pool test.
    print("SMOKE_FIRST_LAUNCH_SETUP", namespace["setup"] is not None)
    namespace["setup"] = None
    print("SMOKE_MONA", "pico3d" if renderer.mona is not None else "fallback")
    for kind in range(4):
        pool.add(kind, 0.5)
    for frame in range(120):
        started = time.ticks_ms()
        update()
        if frame == 60:
            pool.cycle_color()
            pool.water(1, 1)
        badge.update()
        frames.append(time.ticks_diff(time.ticks_ms(), started))
    print("SMOKE_OK frames", len(frames), "average_ms", sum(frames) / len(frames),
          "worst_ms", max(frames), "objects", len(pool.objects),
          "size", screen.width, screen.height)
    start = time.ticks_ms()
    for _ in range(20):
        pool.step(1 / 30, 0.35, -0.2, 0.3, 0.2)
    sim_ms = time.ticks_diff(time.ticks_ms(), start) / 20
    start = time.ticks_ms()
    for _ in range(20):
        badge.clear()
        renderer.draw(pool)
    draw_ms = time.ticks_diff(time.ticks_ms(), start) / 20
    print("SMOKE_PROFILE simulation_ms", sim_ms, "render_ms", draw_ms)
    for obj in pool.objects:
        start = time.ticks_ms()
        for _ in range(10):
            renderer.draw_object(obj)
        size = len(renderer.meshes[obj[6]].vertices) if obj[6] < 3 else "mona"
        print("SMOKE_OBJECT", obj[6], "vertices", size,
              "average_ms", time.ticks_diff(time.ticks_ms(), start) / 10)
    # Worst case under the drop rules: each word once, the rest Monas.
    for weight in (1.4, 0.4, 1.3, 0.8, 1.5):
        pool.add(3, weight)
    start = time.ticks_ms()
    for _ in range(20):
        badge.clear()
        pool.step(1 / 30, -0.8, 0.8, -1, 1)
        renderer.draw(pool)
        badge.update()
    print("SMOKE_MAX_OBJECTS", len(pool.objects), "average_ms",
          time.ticks_diff(time.ticks_ms(), start) / 20)
    for _ in range(150):
        pool.step(1 / 30)
    start = time.ticks_ms()
    for _ in range(20):
        badge.clear()
        pool.step(1 / 30)
        renderer.draw(pool)
        badge.update()
    print("SMOKE_SETTLED_MAX", len(pool.objects), "average_ms",
          time.ticks_diff(time.ticks_ms(), start) / 20,
          "sunk", sum(o[1] < o[19] - 0.2 for o in pool.objects))
    del pool.objects[6:]
    pool.color_index = 0
    pool.tilt_x, pool.tilt_z = 0.08, -0.04
    pool.view_x, pool.view_z = 0.02, -0.025
    pool.level = pool.target_level = -0.08
    pool.disturb(0.25, 0, 0.8)
    for _ in range(20):
        pool.step(1 / 60, 0.08, -0.04)
    renderer.level_until = 0
    renderer.last_level = pool.target_level
    # Words and a light Mona float; a heavy Mona rests on the floor.
    for obj, position in zip(pool.objects, ((0.0, 0.30), (-0.62, -0.36), (0.55, -0.30),
                                            (0.78, 0.30), (-0.55, 0.1), (0.3, -0.1))):
        obj[0], obj[2] = position
        if obj[18] >= 1:
            obj[1] = BOTTOM + REST[obj[6]]
        else:
            obj[1] = pool.surface(obj[0], obj[2]) + (0.025 if obj[6] < 3 else -0.05)
        obj[7] = True
    del pool.drops[:]
    # Drop one more Mona and catch it a moment after its heavy landing.
    pool.serial = 1
    pool.add(3, 0.9)
    for _ in range(60):
        pool.step(1 / 30, 0.08, -0.04)
        if pool.objects[-1][7]:
            break
    for _ in range(5):
        pool.step(1 / 30, 0.08, -0.04)
    # Confirm alpha actually mixes RGB565 pixels rather than replacing them.
    screen.pen = color.rgb(70, 240, 120)
    screen.rectangle(8, 8, 4, 4)
    offset = 9 * screen.stride + 9 * 2
    before = bytes(screen.raw[offset:offset + 2])
    screen.pen = renderer.body
    screen.rectangle(8, 8, 4, 4)
    after = bytes(screen.raw[offset:offset + 2])
    screen.pen = color.rgb(10, 110, 151)
    screen.rectangle(8, 8, 4, 4)
    opaque = bytes(screen.raw[offset:offset + 2])
    assert before != after and after != opaque
    print("SMOKE_ALPHA_OK")
    # Leave a representative final frame available for capture.
    badge.clear()
    renderer.draw(pool)
    print("SCREENSHOT_BEGIN", screen.width, screen.height, screen.stride)
    for y in range(screen.height):
        row = screen.raw[y * screen.stride:(y + 1) * screen.stride]
        print(binascii.b2a_base64(row).decode().strip())
    print("SCREENSHOT_END")


namespace["run"] = bounded_run
app_file = ("/remote/splashy_badge/__init__.py" if is_dir("/remote/splashy_badge")
            else "/system/apps/splashy_badge/__init__.py")
exec(open(app_file).read(), namespace)
