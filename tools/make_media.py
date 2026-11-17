#!/usr/bin/env python3
"""Generate the legacy multi-camera sample set with burned-in frame numbers.

Two backends:

* mp4 (original): numpy + PIL + ffmpeg/PyAV, H.264 clips with B-frames and
  sine-tone audio. Used when those optional dependencies are installed.
* pack (stdlib): the self-contained PNG camera packages produced by the
  same drawing code through multicam.imglib. Used in environments without
  any video library.

Both backends keep the same four-camera geometry (30/25/24/15 fps, camB
ends early) and the 24-bit frame-number strip, so the kernel tests are
backend-agnostic.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multicam.imglib import Canvas, draw_text, write_png
from tools.make_synced_media import write_wav

W, H = 320, 240
SR = 44100
STRIP_BITS, STRIP_H = 24, 8

SPECS = [
    # name    fps  dur(s) bframes gop  bg color           tone Hz
    ("camA", 30, 6.0, 2, 60, (28, 62, 122), 440.0),
    ("camB", 25, 4.0, 2, 50, (122, 44, 44), 550.0),   # ends early
    ("camC", 24, 6.0, 0, 48, (32, 110, 62), 660.0),   # no B-frames
    ("camD", 15, 5.0, 2, 30, (112, 92, 30), 330.0),
]
TB_DEN = 122880


def mp4_backend_available():
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
        import av  # noqa: F401
        import shutil
        return shutil.which("ffmpeg") is not None
    except ImportError:
        return False


def _draw_legacy_frame(name, fps, bg, n):
    img = Canvas(W, H, bg)
    x = (n * 7) % (W - 48)
    img.fill_rect(x, 96, x + 48, 144, (225, 225, 225))
    draw_text(img, 10, 8, f"{name} F{n:05d}", (255, 255, 255), scale=2)
    draw_text(img, 10, 32, f"T{n / fps:7.3f}S", (255, 255, 150), scale=2)
    for bit in range(STRIP_BITS):
        on = (n >> bit) & 1
        img.fill_rect(bit * 8, H - STRIP_H, bit * 8 + 7, H - 1,
                      (255, 255, 255) if on else (0, 0, 0))
    img.outline_rect(0, H - STRIP_H - 2, STRIP_BITS * 8 + 1, H - 1,
                     (255, 0, 0))
    return img


def build_pack_clip(name, fps, dur, bg, tone, media_dir):
    cam_dir = os.path.join(media_dir, name)
    frames_dir = os.path.join(cam_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    n_frames = int(round(fps * dur))
    records = []
    for n in range(n_frames):
        fname = f"f_{n:05d}.png"
        _draw_legacy_frame(name, fps, bg, n).save(
            os.path.join(frames_dir, fname))
        t = n / fps
        records.append({"file": fname, "frame_index": n,
                        "pts": int(round(t * TB_DEN)), "time": round(t, 6),
                        "time_master": round(t, 6),
                        "pict": "I" if n == 0 else "P",
                        "key_frame": n == 0, "event_id": None,
                        "gap_after": False, "missing_before": n > 0 and False})
    write_wav(os.path.join(cam_dir, "audio.wav"), tone, dur)
    meta = {"name": name, "fps": fps, "offset": 0.0, "width": W,
            "height": H, "time_base": [1, TB_DEN], "drift": 1.0,
            "jitter": 0.0, "coverage_master": [0.0, dur], "gaps": [],
            "non_uniform": False, "tone_hz": tone, "frames": records}
    with open(os.path.join(cam_dir, "camera.json"), "w",
              encoding="utf-8") as fh:
        json.dump(meta, fh)
    return cam_dir


def build_mp4_clip(name, fps, dur, bf, gop, bg, tone, out_path):
    """Original H.264 path — only invoked with the full optional stack."""
    import subprocess
    import tempfile
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        ffmpeg = "ffmpeg"

    def font(size):
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()

    def make_frame(n):
        img = Image.new("RGB", (W, H), bg)
        d = ImageDraw.Draw(img)
        x = (n * 7) % (W - 48)
        d.rectangle([x, 96, x + 48, 144], fill=(225, 225, 225))
        d.text((10, 8), f"{name} frame {n:05d}", fill=(255, 255, 255),
               font=font(26))
        d.text((10, 42), f"t={n / fps:7.3f}s", fill=(255, 255, 150),
               font=font(18))
        for i in range(STRIP_BITS):
            bit = (n >> i) & 1
            d.rectangle([i * 8, H - STRIP_H, i * 8 + 7, H - 1],
                        fill=(255, 255, 255) if bit else (0, 0, 0))
        d.rectangle([0, H - STRIP_H - 2, STRIP_BITS * 8 + 1, H - 1],
                    outline=(255, 0, 0))
        return np.asarray(img)

    n_frames = int(round(fps * dur))
    t = np.arange(int(SR * dur)) / SR
    audio = (np.sin(2 * np.pi * tone * t) * 0.35 * 32767).astype("<i2")
    with tempfile.NamedTemporaryFile(suffix=".s16le", delete=False) as af:
        audio.tofile(af)
        audio_path = af.name
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
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
            proc.stdin.write(make_frame(n).tobytes())
        proc.stdin.close()
        rc = proc.wait()
    finally:
        os.unlink(audio_path)
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed for {name} (rc={rc})")


def ensure_media(media_dir):
    """Create the legacy sample set using the best backend available."""
    os.makedirs(media_dir, exist_ok=True)
    paths = {}
    use_mp4 = mp4_backend_available()
    for name, fps, dur, bf, gop, bg, tone in SPECS:
        if use_mp4:
            out = os.path.join(media_dir, f"{name}.mp4")
            if not os.path.exists(out):
                print(f"[make_media] building {out} ({fps}fps {dur}s bf={bf})")
                build_mp4_clip(name, fps, dur, bf, gop, bg, tone, out)
            paths[name] = out
        else:
            out = os.path.join(media_dir, name)
            if not os.path.isfile(os.path.join(out, "camera.json")):
                print(f"[make_media] stdlib pack {out} ({fps}fps {dur}s)")
                build_pack_clip(name, fps, dur, bg, tone, media_dir)
            paths[name] = out
    return paths


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "media_legacy")
    ensure_media(target)
    print("done")
