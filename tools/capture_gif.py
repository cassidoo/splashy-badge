"""Record docs/splash.gif from a connected badge (needs Pillow and an installed app)."""

import base64
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image

root = Path(__file__).resolve().parents[1]
port = sys.argv[1]
result = subprocess.run(
    [sys.executable, "-m", "mpremote", "connect", port, "run", str(root / "tools" / "gif_scene.py")],
    capture_output=True, text=True, timeout=900)
lines = result.stdout.splitlines()
if result.returncode or "GIF_DONE" not in lines:
    print(result.stdout[-3000:], result.stderr, file=sys.stderr)
    sys.exit(1)
frames = []
for i, line in enumerate(lines):
    if not line.startswith("FRAME_BEGIN"):
        continue
    _, width, height, stride = line.split()
    width, height = int(width), int(height)
    pixels = bytearray()
    for row in lines[i + 1:i + 1 + height]:
        for (p,) in struct.iter_unpack("<H", base64.b64decode(row)):
            pixels += bytes(((p >> 11) * 255 // 31, ((p >> 5) & 63) * 255 // 63, (p & 31) * 255 // 31))
    frames.append(Image.frombytes("RGB", (width, height), bytes(pixels)))
palette = frames[len(frames) // 3].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
frames = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
out = root / "docs" / "splash.gif"
frames[0].save(out, save_all=True, append_images=frames[1:], duration=33, loop=0, optimize=True)
print("Wrote %s (%d frames, %d KB)" % (out, len(frames), out.stat().st_size // 1024))
