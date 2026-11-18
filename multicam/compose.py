"""Composite renderer: draws every stream into ONE image.

Layout per cell: top bar (name + coloured state badge), video area,
bottom bar (actual picked pts / target / error / decode-order info).
Missing frames are drawn as a dark placeholder with the state spelled
out — a stalled or ended camera is visible, never silently dropped.
"""
import io
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CELL_W, CELL_H = 480, 360
TOP_BAR, BOT_BAR = 26, 34

STATE_COLORS = {
    "OK": (60, 180, 90),
    "STALLED": (235, 150, 40),
    "HELD": (220, 200, 60),
    "ENDED": (90, 120, 200),
    "NOT_STARTED": (130, 130, 130),
    "ERROR": (220, 60, 60),
    "GAP": (230, 90, 200),
    "INIT": (130, 130, 130),
}


def _font(size):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


F_TOP = _font(16)
F_BOT = _font(13)
F_BIG = _font(28)


def grid_shape(n):
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows


class CellView:
    def __init__(self, name, state, image, line1="", line2=""):
        self.name = name
        self.state = state
        self.image = image          # HxWx3 uint8 or None
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
        img = Image.new("RGB", (self.width, self.height), (18, 18, 22))
        d = ImageDraw.Draw(img)
        for i, cell in enumerate(cells):
            col, row = i % self.cols, i // self.cols
            x0 = col * self.cw
            y0 = row * (self.ch + TOP_BAR + BOT_BAR)
            self._draw_cell(d, img, cell, x0, y0)
        return img

    def _draw_cell(self, d, img, cell, x0, y0):
        color = STATE_COLORS.get(cell.state, (130, 130, 130))
        # top bar
        d.rectangle([x0, y0, x0 + self.cw - 1, y0 + TOP_BAR - 1], fill=(35, 35, 42))
        d.text((x0 + 8, y0 + 5), cell.name, fill=(240, 240, 240), font=F_TOP)
        badge = cell.state
        tw = d.textlength(badge, font=F_TOP)
        d.rectangle([x0 + self.cw - tw - 18, y0 + 4, x0 + self.cw - 6,
                     y0 + TOP_BAR - 4], fill=color)
        d.text((x0 + self.cw - tw - 12, y0 + 5), badge,
               fill=(10, 10, 10), font=F_TOP)
        # video area
        vy = y0 + TOP_BAR
        if cell.image is not None:
            frame = Image.fromarray(cell.image).resize(
                (self.cw, self.ch), Image.LANCZOS)
            img.paste(frame, (x0, vy))
        else:
            d.rectangle([x0, vy, x0 + self.cw - 1, vy + self.ch - 1],
                        fill=(28, 28, 34))
            msg = cell.state
            tw = d.textlength(msg, font=F_BIG)
            d.text((x0 + (self.cw - tw) / 2, vy + self.ch / 2 - 18), msg,
                   fill=color, font=F_BIG)
        d.rectangle([x0, vy, x0 + self.cw - 1, vy + self.ch - 1],
                    outline=(60, 60, 70))
        # bottom bar
        by = vy + self.ch
        d.rectangle([x0, by, x0 + self.cw - 1, by + BOT_BAR - 1],
                    fill=(35, 35, 42))
        d.text((x0 + 8, by + 3), cell.line1, fill=(200, 210, 220), font=F_BOT)
        d.text((x0 + 8, by + 18), cell.line2, fill=(160, 170, 180), font=F_BOT)

    def render_png(self, cells):
        buf = io.BytesIO()
        self.render(cells).save(buf, format="PNG")
        return buf.getvalue()


def read_frame_number(composite, index, n_cells, cell_w=CELL_W, cell_h=CELL_H):
    """Read back the 24-bit frame-number strip burned into the source
    clip, from cell ``index`` of a composite image (HxWx3 uint8).
    Bit i sits in an 8x8 block at source x=i*8, scaled to the cell."""
    cols, _ = grid_shape(n_cells)
    col, row = index % cols, index // cols
    x_base = col * cell_w
    y_base = row * (cell_h + TOP_BAR + BOT_BAR) + TOP_BAR
    sx = cell_w / 320.0
    sy = cell_h / 240.0
    value = 0
    for i in range(24):
        x = int(x_base + (i * 8 + 4) * sx)
        y = int(y_base + (240 - 4) * sy)
        r, g, b = (int(v) for v in composite[y, x][:3])
        if (r + g + b) / 3 > 128:
            value |= 1 << i
    return value


def read_event_id(composite, index, n_cells, n_bits=6, cell_w=CELL_W,
                  cell_h=CELL_H):
    """Read back the event-id strip (source y = H-18, bits left to right).

    A value of 0 means no event banner is on screen; equal non-zero ids
    across cells at the same T prove the cameras show the same event."""
    cols, _ = grid_shape(n_cells)
    col, row = index % cols, index // cols
    x_base = col * cell_w
    y_base = row * (cell_h + TOP_BAR + BOT_BAR) + TOP_BAR
    sx = cell_w / 320.0
    sy = cell_h / 240.0
    value = 0
    for i in range(n_bits):
        x = int(x_base + (i * 8 + 4) * sx)
        y = int(y_base + (240 - 18) * sy)
        r, g, b = (int(v) for v in composite[y, x][:3])
        if (r + g + b) / 3 > 128:
            value |= 1 << i
    return value
