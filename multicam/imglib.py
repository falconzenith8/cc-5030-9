"""Pure-stdlib RGB raster, PNG codec and drawing primitives.

No third-party imaging library is available in the target environment, so
the whole pipeline (source frame generation, composite rendering, frame
read-back) runs on bytearrays + zlib.  The PNG output is ordinary PNG 2.0
(colour type 2, 8-bit) that ImageMagick and browsers read directly.
"""
import struct
import zlib

# --------------------------------------------------------------------- PNG
def write_png(path, width, height, rgb):
    """Write an RGB8 raster (bytearray/bytes of length width*height*3).

    ``path`` may be a filesystem path or any binary file-like object.
    """
    if len(rgb) != width * height * 3:
        raise ValueError(f"raster size {len(rgb)} != {width}x{height}x3")

    def chunk(tag, data):
        c = tag + data
        return (struct.pack(">I", len(data)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF))

    stride = width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (None) — frames are zlib-compressed anyway
        raw.extend(rgb[y * stride:(y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    payload = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
               + chunk(b"IDAT", zlib.compress(bytes(raw), 1))
               + chunk(b"IEND", b""))
    if hasattr(path, "write"):
        path.write(payload)
    else:
        with open(path, "wb") as fh:
            fh.write(payload)


def read_png(path):
    """Read an RGB/RGBA/gray PNG. Returns (width, height, colour_type, bytes).

    Supports the filter types produced by encoders in normal use (0-4) and
    the colour types used by this project's own writer.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    pos = 8
    idat = bytearray()
    width = height = bit_depth = colour_type = None
    palette = None
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += length + 12
        if tag == b"IHDR":
            width, height, bit_depth, colour_type = struct.unpack(
                ">IIBB", body[:10])
            if bit_depth != 8:
                raise ValueError("only 8-bit PNGs are supported")
        elif tag == b"PLTE":
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif tag == b"IDAT":
            idat.extend(body)
        elif tag == b"IEND":
            break
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour_type]
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    out = bytearray()
    prev = bytearray(stride)
    rpos = 0
    for _ in range(height):
        ftype = raw[rpos]
        rpos += 1
        line = bytearray(raw[rpos:rpos + stride])
        rpos += stride
        if ftype == 0:
            # filter None: this project's writer emits only this type, so
            # the common path is a bulk copy instead of a per-byte loop
            out.extend(line)
            prev = line
            continue
        bpp = channels
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            x = line[i]
            if ftype == 1:
                x = (x + a) & 0xFF
            elif ftype == 2:
                x = (x + b) & 0xFF
            elif ftype == 3:
                x = (x + ((a + b) >> 1)) & 0xFF
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                x = (x + pr) & 0xFF
            else:
                raise ValueError(f"unsupported PNG filter {ftype}")
            line[i] = x
        out.extend(line)
        prev = line
    if colour_type == 3:
        if palette is None:
            raise ValueError("indexed PNG missing PLTE")
        expanded = bytearray()
        for idx in out:
            expanded.extend(palette[idx])
        return width, height, colour_type, bytes(expanded)
    return width, height, colour_type, bytes(out)


def to_rgb(width, height, colour_type, raw):
    """Normalise any supported colour type to an RGB bytearray."""
    if colour_type in (2, 3):  # type 3 indices are already expanded by read_png
        return bytearray(raw)
    if colour_type == 6:
        out = bytearray(width * height * 3)
        for i in range(width * height):
            out[i * 3:i * 3 + 3] = raw[i * 4:i * 4 + 3]
        return out
    if colour_type == 0:
        out = bytearray(width * height * 3)
        for i, v in enumerate(raw):
            out[i * 3:i * 3 + 3] = bytes((v, v, v))
        return out
    if colour_type == 4:
        out = bytearray(width * height * 3)
        for i in range(width * height):
            v = raw[i * 2]
            out[i * 3:i * 3 + 3] = bytes((v, v, v))
        return out
    raise ValueError(f"unsupported colour type {colour_type}")


def load_rgb(path):
    w, h, ct, raw = read_png(path)
    return w, h, to_rgb(w, h, ct, raw)


# ----------------------------------------------------------------- raster
class Canvas:
    """RGB8 raster with the handful of drawing ops the project needs."""

    def __init__(self, width, height, bg=(0, 0, 0)):
        self.w = width
        self.h = height
        self.buf = bytearray(bytes(bg) * (width * height))

    def put(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i:i + 3] = bytes(color)

    def fill_rect(self, x0, y0, x1, y1, color):
        x0, x1 = max(0, x0), min(self.w - 1, x1)
        y0, y1 = max(0, y0), min(self.h - 1, y1)
        if x1 < x0 or y1 < y0:
            return
        row = bytes(color) * (x1 - x0 + 1)
        for y in range(y0, y1 + 1):
            i = (y * self.w + x0) * 3
            self.buf[i:i + len(row)] = row

    def outline_rect(self, x0, y0, x1, y1, color):
        self.fill_rect(x0, y0, x1, y0, color)
        self.fill_rect(x0, y1, x1, y1, color)
        self.fill_rect(x0, y0, x0, y1, color)
        self.fill_rect(x1, y0, x1, y1, color)

    def paste(self, rgb, src_w, src_h, x0, y0):
        x0c, y0c = max(0, x0), max(0, y0)
        x1 = min(self.w, x0 + src_w)
        y1 = min(self.h, y0 + src_h)
        for y in range(y0c, y1):
            sx = x0c - x0
            dst = (y * self.w + x0c) * 3
            src = ((y - y0) * src_w + sx) * 3
            n = (x1 - x0c) * 3
            self.buf[dst:dst + n] = rgb[src:src + n]

    def resize(self, new_w, new_h):
        """Nearest-neighbour resize (deterministic, dependency-free).

        Integer scaling uses block replication via bulk byte copies; the
        general path builds each output row from source-row slices.
        """
        out = Canvas(new_w, new_h)
        if new_w % self.w == 0 and new_h % self.h == 0:
            sx = new_w // self.w
            sy = new_h // self.h
            src = self.buf
            row3 = self.w * 3
            for y in range(self.h):
                base = y * row3
                expanded = bytearray()
                for x in range(self.w):
                    expanded.extend(src[base + x * 3:base + x * 3 + 3] * sx)
                block = bytes(expanded)
                dst_y0 = y * sy
                for r in range(sy):
                    i = (dst_y0 + r) * new_w * 3
                    out.buf[i:i + new_w * 3] = block
            return out
        xmap = [min(self.w - 1, int(x * self.w / new_w))
                for x in range(new_w)]
        ymap = [min(self.h - 1, int(y * self.h / new_h))
                for y in range(new_h)]
        src = self.buf
        # build each output row once as joined 3-byte pieces, then copy it
        row_pieces = [b""] * new_w
        for y, sy_ in enumerate(ymap):
            src_base = sy_ * self.w * 3
            for x, sx_ in enumerate(xmap):
                row_pieces[x] = src[src_base + sx_ * 3:src_base + sx_ * 3 + 3]
            row = b"".join(row_pieces)
            dst_base = y * new_w * 3
            out.buf[dst_base:dst_base + new_w * 3] = row
        return out

    def pixel(self, x, y):
        i = (y * self.w + x) * 3
        return tuple(self.buf[i:i + 3])

    def save(self, path):
        write_png(path, self.w, self.h, self.buf)


# ------------------------------------------------------------------- GIF
def write_gif(path, frames, delays_ms):
    """Write an animated GIF89a from RGB Canvases using a global median-cut
    palette.  Pure stdlib; used for the offline composite preview summary."""
    if not frames:
        raise ValueError("no frames to encode")
    w, h = frames[0].w, frames[0].h
    palette, n_colors = _median_cut_palette(frames)
    gct_bits = max(1, (n_colors - 1).bit_length())
    gct_size = 1 << gct_bits
    while len(palette) < gct_size:
        palette.append((0, 0, 0))
    rgb_to_idx = {c: i for i, c in enumerate(palette)}

    def index_of(rgb):
        best, bd = 0, 1 << 30
        for i, c in enumerate(palette[:n_colors]):
            d = (c[0] - rgb[0]) ** 2 + (c[1] - rgb[1]) ** 2 + (c[2] - rgb[2]) ** 2
            if d < bd:
                best, bd = i, d
        return best

    out = bytearray()
    out += b"GIF89a"
    # logical screen descriptor + global colour table
    out += struct.pack("<HHBBB", w, h, 0xF0 | (gct_bits - 1), 0, 0)
    for c in palette:
        out += bytes(c)
    # netscape looping extension
    out += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00"
    for img, delay in zip(frames, delays_ms):
        out += b"\x21\xF9\x04\x00" + struct.pack("<H", max(2, delay // 10)) + b"\x00\x00"
        out += b"\x2C" + struct.pack("<HHHH", 0, 0, w, h) + b"\x00"
        indexed = bytearray(w * h)
        buf = img.buf
        for p in range(w * h):
            i = p * 3
            key = (buf[i], buf[i + 1], buf[i + 2])
            indexed[p] = rgb_to_idx.get(key) if key in rgb_to_idx else index_of(key)
        # LZW minimum code size = max(2, bits needed)
        min_code = max(2, gct_bits)
        out += bytes([min_code])
        out += _lzw_encode(indexed, min_code)
        out += b"\x00"  # block terminator
    out += b"\x3B"
    with open(path, "wb") as fh:
        fh.write(bytes(out))


def _median_cut_palette(frames, max_colors=256):
    samples = {}
    step = max(1, (frames[0].w * frames[0].h * len(frames)) // 20000)
    k = 0
    for img in frames:
        buf = img.buf
        for p in range(0, img.w * img.h, 1):
            if k % step == 0:
                samples[bytes(buf[p * 3:p * 3 + 3])] = None
            k += 1
    colors = [tuple(c) for c in samples.keys()]
    if len(colors) <= max_colors:
        return colors, len(colors)
    boxes = [colors]
    while len(boxes) < max_colors:
        boxes.sort(key=lambda b: _box_range(b), reverse=True)
        target = boxes.pop(0)
        if len(target) < 2:
            boxes.append(target)
            break
        channel = max(range(3), key=lambda c: max(p[c] for p in target)
                      - min(p[c] for p in target))
        target.sort(key=lambda c: c[channel])
        mid = len(target) // 2
        boxes.extend((target[:mid], target[mid:]))
    palette = []
    for box in boxes:
        avg = tuple(sum(p[c] for p in box) // len(box) for c in range(3))
        palette.append(avg)
    return palette, len(palette)


def _box_range(box):
    return sum(max(p[c] for p in box) - min(p[c] for p in box) for c in range(3))


def _lzw_encode(indexed, min_code):
    clear = 1 << min_code
    end = clear + 1
    dict_size = end + 1
    code_bits = min_code + 1
    table = {bytes([i]): i for i in range(clear)}
    out = _BitWriter()
    out.write(clear, code_bits)
    w = b""
    for byte in indexed:
        wc = w + bytes([byte])
        if wc in table:
            w = wc
        else:
            out.write(table[w], code_bits)
            if dict_size < 4096:
                table[wc] = dict_size
                dict_size += 1
                if dict_size > (1 << code_bits) and code_bits < 12:
                    code_bits += 1
            else:
                out.write(clear, code_bits)
                table = {bytes([i]): i for i in range(clear)}
                dict_size = end + 1
                code_bits = min_code + 1
            w = bytes([byte])
    if w:
        out.write(table[w], code_bits)
    out.write(end, code_bits)
    return out.blocks()


class _BitWriter:
    def __init__(self):
        self.bits = 0
        self.nbits = 0
        self.bytes = bytearray()

    def write(self, value, width):
        self.bits |= value << self.nbits
        self.nbits += width
        while self.nbits >= 8:
            self.bytes.append(self.bits & 0xFF)
            self.bits >>= 8
            self.nbits -= 8

    def blocks(self):
        if self.nbits:
            self.bytes.append(self.bits & 0xFF)
        out = bytearray()
        for i in range(0, len(self.bytes), 255):
            chunk = self.bytes[i:i + 255]
            out.append(len(chunk))
            out.extend(chunk)
        return bytes(out)


# ------------------------------------------------------------- bitmap font
# A compact 5x7 bitmap font (A-Z, 0-9 and the punctuation the UI needs).
# Each glyph is 7 rows of 5 bits, MSB-first inside each row.
_GLYPHS = {
    " ": ["00000"] * 7,
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    ".": ["00000", "00000", "00000", "00000", "00000", "00110", "00110"],
    ",": ["00000", "00000", "00000", "00000", "00110", "00110", "01000"],
    ":": ["00000", "00110", "00110", "00000", "00110", "00110", "00000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "/": ["00001", "00010", "00100", "01000", "10000", "00000", "00000"],
    "#": ["01010", "01010", "11111", "01010", "11111", "01010", "01010"],
    "=": ["00000", "11111", "00000", "11111", "00000", "00000", "00000"],
    "?": ["01110", "10001", "00010", "00100", "00100", "00000", "00100"],
    "%": ["11001", "11010", "00010", "00100", "01000", "10110", "10011"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
    "_": ["00000", "00000", "00000", "00000", "00000", "00000", "11111"],
    "|": ["00100", "00100", "00100", "00100", "00100", "00100", "00100"],
    "<": ["00010", "00100", "01000", "10000", "01000", "00100", "00010"],
    ">": ["01000", "00100", "00010", "00001", "00010", "00100", "01000"],
    "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
}

GLYPH_W, GLYPH_H = 5, 7


def text_size(text, scale=1):
    return len(text) * (GLYPH_W + 1) * scale, GLYPH_H * scale


def draw_text(canvas, x, y, text, color=(255, 255, 255), scale=1):
    cx = x
    for ch in text.upper():
        rows = _GLYPHS.get(ch, _GLYPHS["?"])
        for ry, row in enumerate(rows):
            for rx, bit in enumerate(row):
                if bit == "1":
                    canvas.fill_rect(cx + rx * scale, y + ry * scale,
                                     cx + (rx + 1) * scale - 1,
                                     y + (ry + 1) * scale - 1, color)
        cx += (GLYPH_W + 1) * scale
    return cx
