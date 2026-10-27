# Agent instructions

This repository contains **Splashy Badge**, a MicroPython app for the GitHub
Universe 2026 badge (RP2350B, USB ID `2e8a:1101`). The badge app is the
`splashy_badge/` folder.

## Deploying to a connected badge

Follow these steps when a user asks you to install or deploy Splashy Badge.

1. **Get the code.** If you aren't already in a checkout of this repository,
   clone it: `git clone https://github.com/cassidoo/splashy-badge`.
2. **Check prerequisites.** You need `python3` (3.8+) and `mpremote`.
   - If `mpremote` is missing, install it with
     `python3 -m pip install --user mpremote`. If that is blocked
     (externally managed Python), use `pipx install mpremote` or
     `brew install mpremote` on macOS.
3. **Find the badge.** Run `mpremote devs` and look for a line containing
   `2e8a:1101`.
   - If there isn't one, ask the user to connect the badge with a USB-C *data*
     cable and wake it.
   - Close other programs that hold the port (Thonny, `screen`, Web Serial
     tabs). **Never run serial commands in parallel:** only one process can own
     the port.
4. **Install.** From the repository root, run `python3 install.py`. Allow
   about two minutes. The script:
   - calls `powman.reset_into_msc()` over serial to enter USB mass-storage mode;
   - waits for the `BADGER` volume, backs up any existing copy into `backups/`,
     and replaces `apps/splashy_badge/` on it;
   - ejects the volume, waits for the serial port to return, and checks the
     SHA-256 of every file under `/system/apps/splashy_badge`;
   - resets the badge.

   Pass `--port <port>` if more than one badge is connected.
5. **Report the result.** On success the script ends with
   `Verified N files in /system/apps/splashy_badge.` Tell the user that Splashy
   Badge is now in the badge menu, that setup opens the first time so they can
   pick their handle, title, and pronouns, and summarise the controls:
   - tilt: slosh the water;
   - right-side Up / Down: water level;
   - bottom Left / Right / Select: drop handle / title / pronouns, then Monas;
   - touch D-pad: wind; A: clear; B: edge color; Menu: setup;
   - Home: quit.

### Troubleshooting

| Symptom | Fix |
| --- | --- |
| `BADGER volume did not appear` | Ask the user to open the badge's **Mass Storage** app, then run `python3 install.py --volume <path>` |
| Volume path on Linux | Usually `/media/$USER/BADGER` or `/run/media/$USER/BADGER`; mount it with `udisksctl mount -b /dev/sdX1` if it isn't automounted |
| Volume path on Windows | The drive letter whose label is `BADGER`, for example `E:\` |
| `Couldn't eject automatically` | Ask the user to eject `BADGER` in their file manager or press the badge's reset button; the installer keeps waiting for two minutes |
| `Device not configured` or a busy port | Another process owns the port. Close it and retry. A `read failed` error from the mode switch itself is expected, because the badge reboots |
| Badge doesn't return to serial after eject | Ask the user to press reset. The files are already copied; confirm with `mpremote connect <port> fs ls :/system/apps/splashy_badge` |
| App crashes on launch with `NameError` or `ImportError` for `badge`, `screen` or `badgeware` | The badge needs the October 2026 (or later) firmware |

### Manual fallback

Use this if `install.py` can't run but the `BADGER` volume is mounted. The
volume root corresponds to `/system` on the badge.

```sh
rm -rf "<BADGER>/apps/splashy_badge"
cp -R splashy_badge "<BADGER>/apps/"
find "<BADGER>/apps" -name '._*' -delete   # macOS only
# macOS: diskutil eject "<BADGER>"   Linux: eject "<BADGER>"   Windows: eject from Explorer
```

### Rules

- Only write to `apps/splashy_badge/` on the badge. Don't modify `main.py`,
  `secrets.py`, other apps, or anything under `/state`. At runtime the app
  itself saves its labels with `badgeware.State` (`/state/splashy_badge.json`).
- Normal REPL mode mounts `/system` read-only. `mpremote fs cp` to
  `:/system/...` fails with `EROFS`, so use mass-storage mode, as `install.py`
  does.
- Remote paths in `mpremote fs` commands start with `:`.

## Developing the app

- Run the tests with `python3 -m unittest discover -s tests` (standard library
  only). Keep them passing.
- `python3 tools/capture_smoke.py <port>` mounts this checkout on a connected
  badge, runs the app for a few seconds, prints frame timings, and saves the
  last frame to `preview.png`. Add `--installed` to test the installed copy.
  Settled frames with nine objects take about 72 ms; keep them under 80 ms.
- The art is generated: edit `tools/build_icon.py` rather than hand-editing
  `splashy_badge/icon.png`, which must stay 24x24 RGBA.
- `splashy_badge/README.md` must start with a one-sentence description, because
  the badge menu uses it.
- MicroPython notes: viper can't shift a constant into the sign bit (`255 << 24`),
  so pass such values in as arguments. Import modules at the top of a file;
  a lazy `import` inside a function can stall for seconds on the badge's
  filesystem.
