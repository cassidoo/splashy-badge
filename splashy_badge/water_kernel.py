"""Machine-code (viper) shading for the water surface; integer maths only.

Inputs are wave heights in thousandths and a 64-step sine table scaled by 100.
Outputs one byte per quad shade, per crest-edge brightness and per glint tilt.
`shading.py` holds the identical pure-Python version used off the badge.
"""
import micropython


@micropython.viper
def shade(wave: ptr32, sines: ptr32, out: ptr8, ta: int, tb: int, tc: int):
    nx = 9
    nz = 5
    for z in range(nz - 1):
        for x in range(nx - 1):
            i = z * nx + x
            h = int(wave[i])
            n = 500 + (int(wave[i + 1]) - h) * 9 // 2 + (int(wave[i + nx]) - h) * 4
            n += int(sines[(x * 17 + z * 23 + ta) & 63]) * 7 // 5
            n = n // 100 if n > 0 else 0
            n = 14 if n > 14 else n
            out[z * 8 + x] = n & 14
            j = i + nx
            k = int(wave[j])
            s = 250 + (k - int(wave[j + 1])) * 3 + (k - h) * 13 // 5
            s += int(sines[(x * 21 - z * 13 + tb) & 63]) * 6 // 5
            out[32 + z * 8 + x] = s // 100 if s > 0 else 0
            if x:
                below = int(wave[j + nx]) if z + 2 < nz else k
                t = (int(wave[j - 1]) - int(wave[j + 1])) * 9 // 5 + (h - below) * 8 // 5
                t += int(sines[(x * 24 + z * 32 + tc) & 63]) * 4 // 5
                out[64 + z * 8 + x] = 250 if t > 250 else t if t > 0 else 0
