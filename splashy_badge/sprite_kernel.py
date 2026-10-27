import micropython


@micropython.viper
def capture(src: ptr16, stride: int, left: int, top: int, dst: ptr32, w: int, h: int,
            sw: int, sh: int, key: int, alpha: int):
    """Copy an RGB565 screen patch into an RGBA sprite; key-coloured pixels become clear."""
    for row in range(h):
        y = top + row
        for col in range(w):
            x = left + col
            value = 0
            if y >= 0 and y < sh and x >= 0 and x < sw:
                p = src[y * stride + x]
                if p != key:
                    r = (p >> 11) & 31
                    g = (p >> 5) & 63
                    b = p & 31
                    value = (((r << 3) | (r >> 2)) | (((g << 2) | (g >> 4)) << 8)
                             | (((b << 3) | (b >> 2)) << 16) | alpha)
            dst[row * w + col] = value
