import base64
import struct
import subprocess
import sys
import zlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
port = sys.argv[1]
command = [sys.executable, "-m", "mpremote", "connect", port]
if "--installed" not in sys.argv:
    command += ["mount", str(root)]
script = next((arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--script=")),
              str(root / "tools" / "hardware_smoke.py"))
command += ["run", script]
result = subprocess.run(
    command,
    capture_output=True, text=True, timeout=180)
lines = result.stdout.splitlines()
for line in lines:
    if line.startswith("SMOKE_") or "Traceback" in line or "Error" in line:
        print(line)
if result.returncode or not any(line.startswith("SMOKE_OK") for line in lines):
    print(result.stdout[-6000:], result.stderr, file=sys.stderr)
    sys.exit(1)
start = next(i for i, line in enumerate(lines) if line.startswith("SCREENSHOT_BEGIN"))
_, width, height, stride = lines[start].split()
width, height, stride = int(width), int(height), int(stride)
rows = [base64.b64decode(line) for line in lines[start + 1:start + 1 + height]]
if len(rows) != height or any(len(row) != stride for row in rows):
    raise RuntimeError("Incomplete framebuffer capture")
if stride == width * 2:
    converted = []
    for row in rows:
        rgb = bytearray()
        for (pixel,) in struct.iter_unpack("<H", row):
            rgb.extend(((pixel >> 11) * 255 // 31, ((pixel >> 5) & 63) * 255 // 63,
                        (pixel & 31) * 255 // 31, 255))
        converted.append(rgb)
    rows = converted
elif stride != width * 4:
    raise RuntimeError("Unsupported framebuffer format")


def chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))


png = b"\x89PNG\r\n\x1a\n"
png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(b"".join(b"\0" + row for row in rows)))
png += chunk(b"IEND", b"")
path = root / "preview.png"
path.write_bytes(png)
print("Captured badge framebuffer:", path)
