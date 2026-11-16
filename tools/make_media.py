#!/usr/bin/env python3
"""Generate self-made multi-camera clips with burned-in frame numbers.

Each clip gets:
  - a visible frame counter + timestamp (drawn with PIL, no fontconfig needed)
  - a 24-bit binary strip in the bottom-left 192x8 px encoding the frame
    number, so automated tests can read the frame number back from any
    composited image (each bit is an 8x8 block, white=1 black=0, LSB first)
  - a distinct sine tone so audio-source selection is audible/verifiable
  - its own fps / B-frame layout / duration
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG = "ffmpeg"

W, H = 320, 240
SR = 44100
STRIP_BITS = 24
STRIP_H = 8

SPECS = [
    # name    fps  dur(s) bframes gop  bg color         tone Hz
    ("camA", 30, 6.0, 2, 60, (28, 62, 122), 440.0),
    ("camB", 25, 4.0, 2, 50, (122, 44, 44), 550.0),   # ends early
    ("camC", 24, 6.0, 0, 48, (32, 110, 62), 660.0),   # no B-frames
    ("camD", 15, 5.0, 2, 30, (112, 92, 30), 330.0),
]


def _font(size):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def make_frame(name, fps, bg, n):
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    x = (n * 7) % (W - 48)
    d.rectangle([x, 96, x + 48, 144], fill=(225, 225, 225))
    d.text((10, 8), f"{name} frame {n:05d}", fill=(255, 255, 255), font=_font(26))
    d.text((10, 42), f"t={n / fps:7.3f}s", fill=(255, 255, 150), font=_font(18))
    # binary strip: bit i -> block [i*8, i*8+7] x [H-8, H-1]
    for i in range(STRIP_BITS):
        bit = (n >> i) & 1
        d.rectangle([i * 8, H - STRIP_H, i * 8 + 7, H - 1],
                    fill=(255, 255, 255) if bit else (0, 0, 0))
    d.rectangle([0, H - STRIP_H - 2, STRIP_BITS * 8 + 1, H - 1], outline=(255, 0, 0))
    return np.asarray(img)


def make_tone(freq, dur):
    t = np.arange(int(SR * dur)) / SR
    return (np.sin(2 * np.pi * freq * t) * 0.35 * 32767).astype("<i2")


def build_clip(name, fps, dur, bf, gop, bg, tone, out_path):
    n_frames = int(round(fps * dur))
    with tempfile.NamedTemporaryFile(suffix=".s16le", delete=False) as af:
        make_tone(tone, dur).tofile(af)
        audio_path = af.name
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", str(fps), "-i", "pipe:0",
        "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", audio_path,
        "-c:v", "libx264", "-preset", "veryfast",
        "-bf", str(bf), "-g", str(gop), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-shortest", out_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for n in range(n_frames):
            proc.stdin.write(make_frame(name, fps, bg, n).tobytes())
        proc.stdin.close()
        rc = proc.wait()
    finally:
        os.unlink(audio_path)
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed for {name} (rc={rc})")


def ensure_media(media_dir):
    os.makedirs(media_dir, exist_ok=True)
    paths = {}
    for name, fps, dur, bf, gop, bg, tone in SPECS:
        out = os.path.join(media_dir, f"{name}.mp4")
        if not os.path.exists(out):
            print(f"[make_media] building {out} ({fps}fps {dur}s bf={bf})")
            build_clip(name, fps, dur, bf, gop, bg, tone, out)
        paths[name] = out
    return paths


if __name__ == "__main__":
    ensure_media(sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media"))
    print("done")
