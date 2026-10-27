import os
import sys
import time

APP_DIR = next(path for path in (
    "/remote/splashy_badge", "/system/apps/splashy_badge"
) if is_dir(path))
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

from physics import Pool, Motion, set_label_widths
from controls import Controls
from render import Renderer
import nametag

badge.mode(HIRES | VSYNC)
badge.default_clear = color.rgb(5, 12, 23)
screen.antialias = image.OFF
screen.fill_rule = image.EVEN_ODD



def github_username():
    """The badge owner's handle, as set for the built-in Badge app."""
    try:
        import secrets
        name = str(getattr(secrets, "GITHUB_USERNAME", "") or "").strip()
        if name:
            return name
    except ImportError:
        pass
    try:
        import json
        with open("/state/badge_user.json") as file:
            return json.load(file).get("login") or None
    except (OSError, ValueError, AttributeError):
        return None


pool = Pool()
username = github_username()
labels, labels_saved = nametag.load(username=username)
controls = Controls(BUTTON_UP, BUTTON_DOWN, BUTTON_LEFT, BUTTON_RIGHT,
                    BUTTON_SELECT, BUTTON_BACK, labels)
SETUP_BUTTONS = {"up": BUTTON_UP, "down": BUTTON_DOWN, "left": BUTTON_LEFT,
                 "right": BUTTON_RIGHT, "select": BUTTON_SELECT, "back": BUTTON_BACK,
                 "menu": BUTTON_MENU}
# Give the firmware's shared IMU poller time to populate its first sample.
for _ in range(12):
    badge.poll()
    time.sleep_ms(10)
motion = Motion(badge.imu())
try:
    import pico3d
    from floaty_mona import MonaDrawer
    mona = MonaDrawer(pico3d, screen, color, image=image, vec2=vec2)
except (ImportError, OSError, ValueError, MemoryError) as error:
    print("Splashy Badge: Mona model unavailable:", error)
    mona = None
renderer = Renderer(screen, color, font, shape, mat3, mona)
set_label_widths(renderer.set_labels(labels))
last_inverted = badge.upside_down()
notice_until = 0
# First launch opens setup so new owners can pick their own words.
setup = None if labels_saved else nametag.Setup(
    screen, color, font, labels, SETUP_BUTTONS, username, welcome=True)


def pressed(button):
    # Setup accepts the touch pad or the matching physical button.
    return badge.pad.pressed(button) or badge.buttons.pressed(button)


def configure():
    """Run the label setup screen; returns True on frames it handles."""
    global setup, motion, labels_saved
    if setup is None:
        if not badge.pad.pressed(BUTTON_MENU):
            return False
        setup = nametag.Setup(screen, color, font, labels, SETUP_BUTTONS, username)
    elif not setup.update(pressed):
        changed = [kind for kind in range(len(labels)) if setup.labels[kind] != labels[kind]]
        if changed:
            setup.draw_busy()
            badge.update()
            labels[:] = setup.labels
            set_label_widths(renderer.set_labels(labels, changed))
            # Words with old text leave the pool so the new ones can drop in.
            pool.remove(changed)
        if changed or not labels_saved:
            labels_saved = nametag.save(labels)
        setup = None
        # Leaving setup recenters motion at however the badge is now held.
        motion = Motion(badge.imu())
        # Swallow this frame so the closing press doesn't also drop a word.
        return True
    setup.draw()
    return True


def update():
    global last_inverted, motion, notice_until
    dt = min(0.1, badge.ticks_delta / 1000)
    inverted = badge.upside_down()
    if configure():
        return
    if inverted != last_inverted:
        motion = Motion(badge.imu())
        last_inverted = inverted
    wind_x, wind_z, full = controls.apply(badge, pool, dt)
    if full:
        notice_until = badge.ticks + 1800
    tilt_x, tilt_z = motion.read(badge.imu(), dt, inverted)
    pool.step(dt, tilt_x, tilt_z, wind_x, wind_z)
    renderer.draw(pool, wind_x, wind_z, badge.ticks < notice_until)


run(update)
