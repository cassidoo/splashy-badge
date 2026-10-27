import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = "splashy_badge"
SOURCE = ROOT / APP
MPREMOTE = [sys.executable, "-m", "mpremote"]

MENU_MARKER = "# menu_icon.json hook (added by splashy-badge install.py --menu-icon)"
MENU_ANCHOR = '            icon_key = slug if slug in ICONS else "default"\n'
MENU_HOOK = (
    "            " + MENU_MARKER + "\n"
    "            if slug not in ICONS and file_exists(f\"{path}/menu_icon.json\"):\n"
    "                try:\n"
    "                    with open(f\"{path}/menu_icon.json\") as icon_file:\n"
    "                        ICONS[slug] = tuple(tuple(c) for c in json.load(icon_file))\n"
    "                except (OSError, ValueError):\n"
    "                    pass\n"
)


def remote(*args, timeout=30, check=True):
    return subprocess.run(MPREMOTE + list(args), text=True, capture_output=True,
                          timeout=timeout, check=check)


def ports():
    return [line.split()[0] for line in remote("devs").stdout.splitlines()
            if "2e8a:1101" in line]


def wait_for(find, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = find()
        if result:
            return result
        time.sleep(1)
    raise RuntimeError("Timed out waiting for badge. Check its USB connection and mode.")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_error(function, path, error):
    # macOS can remove an AppleDouble sidecar when its paired file is removed.
    if isinstance(error[1], FileNotFoundError) and Path(path).name.startswith("._"):
        print("macOS already removed metadata sidecar: %s" % path, flush=True)
        return
    raise error[1]


def volume_candidates():
    """Places the badge's BADGER mass-storage volume usually appears."""
    if sys.platform == "darwin":
        return [Path("/Volumes/BADGER")]
    if sys.platform.startswith("win"):
        import ctypes
        found = []
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            label = ctypes.create_unicode_buffer(64)
            if ctypes.windll.kernel32.GetVolumeInformationW(
                    "%s:\\" % letter, label, 64, None, None, None, None, 0):
                if label.value.upper() == "BADGER":
                    found.append(Path("%s:\\" % letter))
        return found
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    return [Path("/media", user, "BADGER"), Path("/run/media", user, "BADGER"),
            Path("/media/BADGER"), Path("/mnt/BADGER")]


def find_volume():
    return next((path for path in volume_candidates() if path.is_dir()), None)


def eject(volume):
    if sys.platform == "darwin":
        command = ["diskutil", "eject", str(volume)]
    elif sys.platform.startswith("win"):
        drive = str(volume).rstrip("\\")
        command = ["powershell", "-NoProfile", "-Command",
                   "(New-Object -ComObject Shell.Application).Namespace(17)"
                   ".ParseName('%s').InvokeVerb('Eject')" % drive]
    else:
        command = ["udisksctl", "unmount", "--no-user-interaction", "-p",
                   "block_devices/" + Path(subprocess.run(
                       ["findmnt", "-n", "-o", "SOURCE", str(volume)],
                       capture_output=True, text=True).stdout.strip()).name]
    try:
        return subprocess.run(command, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def patch_menu_source(source):
    """Let the menu draw an app's own white menu_icon.json glyph. Returns None if unsupported."""
    if MENU_MARKER in source:
        return source
    if source.count(MENU_ANCHOR) != 1 or "\nimport os\n" not in source:
        return None
    if "\nimport json\n" not in source:
        source = source.replace("\nimport os\n", "\nimport json\nimport os\n", 1)
    return source.replace(MENU_ANCHOR, MENU_HOOK + MENU_ANCHOR, 1)


def patch_menu(volume):
    menu = volume / "apps" / "menu" / "app.py"
    if not menu.is_file():
        print("No menu/app.py on this badge; skipping the menu icon.", flush=True)
        return
    original = menu.read_text()
    patched = patch_menu_source(original)
    if patched is None:
        print("This menu version isn't recognised; skipping the menu icon.", flush=True)
    elif patched == original:
        print("Menu already shows app icons.", flush=True)
    else:
        backup = ROOT / "backups" / ("menu-app-" + time.strftime("%Y%m%d-%H%M%S") + ".py")
        backup.parent.mkdir(exist_ok=True)
        backup.write_text(original)
        menu.write_text(patched)
        if menu.read_text() != patched:
            raise RuntimeError("USB copy of menu/app.py did not match")
        print("Menu patched to show the droplet; original saved to %s" % backup, flush=True)
    for metadata in (menu.parent / "._app.py",):
        try:
            metadata.unlink()
        except FileNotFoundError:
            pass


def deploy(port=None, volume=None, menu_icon=False):
    if volume is None:
        detected = ports()
        if port is None and len(detected) != 1:
            raise RuntimeError("Connect one badge, or select it with --port.")
        port = port or detected[0]
        volume = find_volume()
        if volume is None:
            print("Switching badge to mass storage.", flush=True)
            try:
                remote("connect", port, "exec", "import powman; powman.reset_into_msc()",
                       timeout=15, check=False)
            except subprocess.TimeoutExpired:
                print("Serial mode-switch timed out; checking for the USB volume.", flush=True)
            try:
                volume = wait_for(find_volume, 45)
            except RuntimeError:
                raise RuntimeError("BADGER volume did not appear. Open the badge's Mass Storage "
                                   "app, then rerun with --volume <path to BADGER>.")
    volume = Path(volume)
    if not (volume / "apps").is_dir() or not (volume / "main.py").is_file():
        raise RuntimeError("Not a badge system volume: %s" % volume)
    dest = volume / "apps" / APP
    if dest.is_symlink():
        raise RuntimeError("Refusing to replace a symlink at %s" % dest)
    if dest.exists():
        backup = ROOT / "backups" / ("splashy-badge-" + time.strftime("%Y%m%d-%H%M%S"))
        shutil.copytree(dest, backup, copy_function=shutil.copyfile,
                        ignore=shutil.ignore_patterns("._*"))
        print("Existing app backed up to %s" % backup, flush=True)
        shutil.rmtree(dest, onerror=remove_error)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".*")
    shutil.copytree(SOURCE, dest, copy_function=shutil.copyfile, ignore=ignore)
    expected = {p.relative_to(SOURCE).as_posix(): digest(p) for p in SOURCE.rglob("*")
                if p.is_file() and not any(part.startswith(".") or part == "__pycache__"
                                          for part in p.relative_to(SOURCE).parts)
                and p.suffix != ".pyc"}
    for name, sha in expected.items():
        if digest(dest / name) != sha:
            raise RuntimeError("USB copy did not match source: " + name)
    # macOS writes AppleDouble "._" sidecars, including one beside the app folder.
    for metadata in list(dest.rglob("._*")) + [volume / "apps" / ("._" + APP)]:
        try:
            metadata.unlink()
        except FileNotFoundError:
            pass
    if menu_icon:
        patch_menu(volume)
    if hasattr(os, "sync"):
        os.sync()
    print("Copied %d files; ejecting badge." % len(expected), flush=True)
    if not eject(volume):
        print("Couldn't eject automatically. Eject BADGER from your file manager "
              "(or press the badge's reset button) to finish.", flush=True)
    port = wait_for(lambda: next((p for p in ports() if not port or p == port), None), 120)
    time.sleep(1)
    script = (
        "import hashlib, binascii\n"
        "def walk(path, rel=''):\n"
        " for entry in __import__('os').ilistdir(path):\n"
        "  name=entry[0]\n"
        "  if entry[1]==0x4000: walk(path+'/'+name, rel+name+'/')\n"
        "  else:\n"
        "   h=hashlib.sha256()\n"
        "   with open(path+'/'+name,'rb') as f:\n"
        "    while True:\n"
        "     b=f.read(1024)\n"
        "     if not b: break\n"
        "     h.update(b)\n"
        "   print(rel+name, binascii.hexlify(h.digest()).decode())\n"
        "walk('/system/apps/%s')\n" % APP
    )
    output = remote("connect", port, "exec", script).stdout
    found = dict(line.split() for line in output.splitlines() if line.strip())
    if found != expected:
        raise RuntimeError("On-badge file hashes do not match the local app: " + output)
    remote("connect", port, "reset")
    print("Verified %d files in /system/apps/%s." % (len(found), APP), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install Splashy Badge without changing other apps.")
    parser.add_argument("--port")
    parser.add_argument("--volume", type=Path)
    parser.add_argument("--menu-icon", action="store_true",
                        help="also patch the home menu so it draws the droplet icon "
                             "(backs up menu/app.py; a firmware update undoes it)")
    args = parser.parse_args()
    try:
        deploy(args.port, args.volume, args.menu_icon)
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print("Installation failed: %s" % error, file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stdout or "", error.stderr or "", file=sys.stderr)
        sys.exit(1)
