"""Integer surface shading shared by the viper kernel and host tests."""
import math
from array import array

from physics import NX, NZ

SINES = array("i", (int(round(math.sin(n * 6.2832 / 64) * 100)) for n in range(64)))
# Radians per second become 64ths of a turn per second.
TURN = 64 / 6.2832


def shade(wave, sines, out, ta, tb, tc):
    for z in range(NZ - 1):
        for x in range(NX - 1):
            i = z * NX + x
            h = wave[i]
            n = 500 + (wave[i + 1] - h) * 9 // 2 + (wave[i + NX] - h) * 4
            n += sines[(x * 17 + z * 23 + ta) & 63] * 7 // 5
            n = n // 100 if n > 0 else 0
            out[z * 8 + x] = min(14, n) & 14
            j = i + NX
            k = wave[j]
            s = 250 + (k - wave[j + 1]) * 3 + (k - h) * 13 // 5
            s += sines[(x * 21 - z * 13 + tb) & 63] * 6 // 5
            out[32 + z * 8 + x] = s // 100 if s > 0 else 0
            if x:
                below = wave[j + NX] if z + 2 < NZ else k
                t = (wave[j - 1] - wave[j + 1]) * 9 // 5 + (h - below) * 8 // 5
                t += sines[(x * 24 + z * 32 + tc) & 63] * 4 // 5
                out[64 + z * 8 + x] = 250 if t > 250 else t if t > 0 else 0


try:
    from water_kernel import shade
except (ImportError, NameError, SyntaxError):
    pass
