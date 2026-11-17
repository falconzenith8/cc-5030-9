"""Composite renderer: draws every stream into ONE image.

Layout per cell: top bar (name + coloured state badge), video area,
bottom bar (actual picked pts / target / error / decode-order info).
Missing frames are drawn as a dark placeholder with the state spelled
out — a stalled or ended camera is visible, never silently dropped.

Pure-stdlib implementation on top of imglib.Canvas; the public surface
(CellView, Composer, render_png, read_frame_number) is unchanged.
"""
import io
import math

from .imglib import Canvas, draw_text, text_size, write_png

CELL_W, CELL_H = 480, 360
TOP_BAR, BOT_BAR = 26, 34
SRC_W, SRC_H = 320, 240

STATE_COLORS = {
    "OK": (60, 180, 90),
    "STALLED": (235, 150, 40),
    "HELD": (220, 200, 60),
    "ENDED": (90, 120, 200),
    "NOT_STARTED": (130, 130, 130),
    "ERROR": (220, 60, 60),
    "INIT": (130, 130, 130),
    "GAP": (180, 70, 170),
}
BG = (18, 18, 22)
BAR_BG = (35, 35, 42)
LIGHT = (240, 240, 240)
DIM = (200, 210, 220)
DIMMER = (160, 170, 180)
BORDER = (60, 60, 70)


def grid_shape(n):
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows


class CellView:
    def __init__(self, name, state, image, line1="", line2=""):
        self.name = name
        self.state = state
        self.image = image          # rgb bytearray of SRC_W x SRC_H or None
        self.line1 = line1
        self.line2 = line2


class Composer:
    def __init__(self, n_cells, cell_w=CELL_W, cell_h=CELL_H):
        self.n = n_cells
        self.cols, self.rows = grid_shape(n_cells)
        self.cw, self.ch = cell_w, cell_h
        self.width = self.cols * cell_w
        self.height = self.rows * (cell_h + TOP_BAR + BOT_BAR)

    def render(self, cells):
        img = Canvas(self.width, self.height, BG)
        for i, cell in enumerate(cells):
            col, row = i % self.cols, i // self.cols
            x0 = col * self.cw
            y0 = row * (self.ch + TOP_BAR + BOT_BAR)
            self._draw_cell(img, cell, x0, y0)
        return img

    def _draw_cell(self, img, cell, x0, y0):
        color = STATE_COLORS.get(cell.state, (130, 130, 130))
        # top bar
        img.fill_rect(x0, y0, x0 + self.cw - 1, y0 + TOP_BAR - 1, BAR_BG)
        draw_text(img, x0 + 8, y0 + 6, cell.name, LIGHT, scale=2)
        tw, _ = text_size(cell.state, scale=2)
        img.fill_rect(x0 + self.cw - tw - 18, y0 + 4,
                      x0 + self.cw - 6, y0 + TOP_BAR - 4, color)
        draw_text(img, x0 + self.cw - tw - 12, y0 + 6, cell.state,
                  (10, 10, 10), scale=2)
        # video area
        vy = y0 + TOP_BAR
        if cell.image is not None:
            frame = Canvas(SRC_W, SRC_H)
            frame.buf = bytearray(cell.image)
            frame = frame.resize(self.cw, self.ch)
            img.paste(frame.buf, self.cw, self.ch, x0, vy)
        else:
            img.fill_rect(x0, vy, x0 + self.cw - 1, vy + self.ch - 1,
                          (28, 28, 34))
            tw, th = text_size(cell.state, scale=3)
            draw_text(img, x0 + (self.cw - tw) // 2,
                      vy + self.ch // 2 - th // 2, cell.state, color, scale=3)
        img.outline_rect(x0, vy, x0 + self.cw - 1, vy + self.ch - 1, BORDER)
        # bottom bar
        by = vy + self.ch
        img.fill_rect(x0, by, x0 + self.cw - 1, by + BOT_BAR - 1, BAR_BG)
        draw_text(img, x0 + 8, by + 3, cell.line1, DIM, scale=1)
        draw_text(img, x0 + 8, by + 19, cell.line2, DIMMER, scale=1)

    def render_png(self, cells):
        buf = io.BytesIO()
        img = self.render(cells)
        write_png(buf, self.width, self.height, img.buf)
        return buf.getvalue()


def read_frame_number(composite, index, n_cells, cell_w=CELL_W, cell_h=CELL_H):
    """Read back the 24-bit frame-number strip burned into the source clip,
    from cell ``index`` of a composite image.

    ``composite`` is either a Canvas (live/offline stdlib path) or an
    HxWx3 ndarray (legacy PyAV tests).  Bit i sits in an 8x8 block at
    source x=i*8, scaled to the cell; white=1, black=0, LSB first.
    """
    cols, _ = grid_shape(n_cells)
    col, row = index % cols, index // cols
    x_base = col * cell_w
    y_base = row * (cell_h + TOP_BAR + BOT_BAR) + TOP_BAR
    sx = cell_w / SRC_W
    sy = cell_h / SRC_H
    value = 0
    for i in range(24):
        x = int(x_base + (i * 8 + 4) * sx)
        y = int(y_base + (SRC_H - 4) * sy)
        if hasattr(composite, "pixel"):
            r, g, b = composite.pixel(x, y)
        else:  # legacy ndarray path
            r, g, b = (int(v) for v in composite[y, x][:3])
        if (r + g + b) / 3 > 128:
            value |= 1 << i
    return value
