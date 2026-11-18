#!/usr/bin/env python3
"""Generate synchronised multi-camera material for the preview project.

Unlike tools/make_media.py (constant-fps clips) this builder produces
real production-style material and writes, next to the clips, the ground
truth needed to audit synchronisation without trusting any default:

  * several frame rates (one stream is genuinely variable frame rate,
    with non-uniform per-frame intervals baked into its pts);
  * per-camera start offsets on the production timeline T;
  * camera gaps: explicit production-time intervals with no frames at
    all, so a camera covering the interval must visibly hold a frame;
  * common events: at known production times every covering camera burns
    the same event id into the picture, so synchronisation can be proven
    by the image content itself ("same event visible in every cell"),
    not by playing windows side by side.

Outputs (all paths inside the chosen package directory):
  media/<cam>.mp4          self-made clips with frame-number strip,
                           event banner and a per-camera sine track
  ground_truth.json        frame schedule + offsets + gaps + events +
                           the parameters and provenance of the build
  project.json             strict-loading multi-cam preview project

The builder is deterministic: a fixed seed drives the jitter, so a
rebuild produces byte-identical frame schedules and ground truth.
"""
import argparse
import hashlib
import json
import os
import sys
from fractions import Fraction

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 320, 240
SR = 44100
TIME_BASE = 15360                       # ticks per second shared by clips
STRIP_BITS = 24                         # frame-number strip (read_frame_number)
EVENT_BITS = 6                          # event-id strip (ids 1..63)
EVENT_BANNER_H = 30
EVENT_HOLD_MS = 220                     # banner stays visible this long

# --------------------------------------------------------------- scenarios
# Production timeline T runs 0..DURATION seconds.  Local media time of a
# camera is t = T - offset.  Gaps are production-time intervals without
# frames for that camera.
DURATION = 14.0

EVENTS = [
    {"id": 1, "T": 2.0, "label": "CLAP"},
    {"id": 2, "T": 5.0, "label": "LIGHT FLASH"},
    {"id": 3, "T": 8.0, "label": "DOOR SLAM"},
    {"id": 4, "T": 11.0, "label": "CLAP 2"},
]

# name, base fps, offset(s), local coverage (start,end), gaps in T,
# variable?, B-frames, GOP, background, tone Hz
CAMERAS = [
    dict(name="camA", fps=30.0, offset=0.0, cover=(0.0, 14.0), gaps=[],
         variable=False, bf=2, gop=60, bg=(28, 62, 122), tone=440.0),
    dict(name="camB", fps=25.0, offset=0.8, cover=(0.0, 12.5),
         gaps=[(5.9, 7.4)], variable=False, bf=2, gop=50,
         bg=(122, 44, 44), tone=550.0),
    dict(name="camC", fps=24.0, offset=-1.2, cover=(0.0, 14.0),
         gaps=[(3.1, 4.6), (9.2, 10.6)], variable=False, bf=0, gop=48,
         bg=(32, 110, 62), tone=660.0),
    dict(name="camD", fps=20.0, offset=1.5, cover=(0.0, 11.8),
         gaps=[], variable=True, bf=2, gop=40, bg=(112, 92, 30),
         tone=330.0),
]

SEED = 20261118


def _font(size):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


F_TITLE = _font(22)
F_TEXT = _font(16)
F_BANNER = _font(20)


# ------------------------------------------------------------- scheduling
def schedule_camera(spec, rng):
    """Return (frames, gaps_local) where frames is a list of local media
    times with non-uniform spacing, skipping every configured gap.

    Constant-fps cameras still receive a sub-frame jitter (intervals are
    not integer multiples of a grid), so nothing in the pipeline may
    assume uniform spacing.  The variable-fps camera alternates slow and
    fast intervals around its base frame duration.
    """
    base = 1.0 / spec["fps"]
    cover_start, cover_end = spec["cover"]
    frames = []
    t = cover_start
    i = 0
    while t <= cover_end + 1e-9:
        if spec["variable"]:
            factor = 0.55 if i % 2 == 0 else 1.45      # alternating cadence
        else:
            factor = 1.0 + rng.uniform(-0.18, 0.18)    # sub-frame jitter
        t_local = t
        in_gap = any(g0 <= (t_local + spec["offset"]) <= g1
                     for g0, g1 in spec["gaps"])
        if not in_gap:
            frames.append(round(t_local, 6))
        t += base * factor
        i += 1
    # a gap must actually bite: keep the neighbouring frames outside it,
    # and assert there is no frame whose production time lands inside
    gaps_local = [(round(g0 - spec["offset"], 6), round(g1 - spec["offset"], 6))
                  for g0, g1 in spec["gaps"]]
    for lo, hi in gaps_local:
        assert all(not (lo - 1e-9 < f < hi + 1e-9) for f in frames), \
            f"{spec['name']}: frame leaked into gap ({lo},{hi})"
    # keep the final frame at least one nominal step behind the coverage
    # end: x264 can otherwise drop a last frame that sits closer than a
    # frame duration to the stream's nominal duration
    if frames and cover_end - frames[-1] < base * 0.5:
        frames.pop()
        assert frames, f"{spec['name']}: schedule emptied while trimming tail"
    return frames, gaps_local


def active_events(local_t, spec):
    """Events whose banner is on screen at this local media time."""
    T = local_t + spec["offset"]
    return [e for e in EVENTS
            if e["T"] <= T <= e["T"] + EVENT_HOLD_MS / 1000.0]


# ---------------------------------------------------------------- drawing
def draw_frame(spec, idx, local_t):
    img = Image.new("RGB", (W, H), spec["bg"])
    d = ImageDraw.Draw(img)
    # moving marker so ordinary (non-event) frames are visually distinct
    x = (idx * 9) % (W - 48)
    d.rectangle([x, 84, x + 48, 132], fill=(225, 225, 225))
    d.text((10, 6), f"{spec['name']} frame {idx:05d}",
           fill=(255, 255, 255), font=F_TITLE)
    d.text((10, 36), f"t={local_t:7.3f}s  T={local_t + spec['offset']:7.3f}s",
           fill=(255, 255, 150), font=F_TEXT)
    d.text((10, 58), f"fps~{spec['fps']:g} off={spec['offset']:+.2f}s",
           fill=(200, 220, 255), font=F_TEXT)

    evs = active_events(local_t, spec)
    if evs:
        e = evs[0]
        d.rectangle([0, H - 70, W - 1, H - 70 + EVENT_BANNER_H - 1],
                    fill=(20, 20, 20))
        d.text((10, H - 66), f"EVENT {e['id']}:{e['label']} @T={e['T']:.2f}s",
               fill=(255, 220, 60), font=F_BANNER)

    # 24-bit frame-number strip (bottom), kept compatible with the
    # existing read_frame_number() audit helper
    for bit in range(STRIP_BITS):
        on = (idx >> bit) & 1
        d.rectangle([bit * 8, H - 8, bit * 8 + 7, H - 1],
                    fill=(255, 255, 255) if on else (0, 0, 0))
    d.rectangle([0, H - 10, STRIP_BITS * 8 + 1, H - 1], outline=(255, 0, 0))

    # 6-bit event-id strip directly above it: same event id appears in
    # every covering camera, which is the image-level sync evidence
    ev_id = evs[0]["id"] if evs else 0
    for bit in range(EVENT_BITS):
        on = (ev_id >> bit) & 1
        d.rectangle([bit * 8, H - 22, bit * 8 + 7, H - 15],
                    fill=(255, 255, 255) if on else (0, 0, 0))
    d.rectangle([0, H - 24, EVENT_BITS * 8 + 1, H - 14],
                outline=(0, 255, 0))
    return np.asarray(img), ev_id


# --------------------------------------------------------------- encoding
def build_clip(spec, frame_times, out_path):
    container = av.open(out_path, "w")
    try:
        vs = container.add_stream("libx264", rate=TIME_BASE)
        vs.time_base = Fraction(1, TIME_BASE)
        vs.width, vs.height = W, H
        vs.pix_fmt = "yuv420p"
        vs.options = {"bf": str(spec["bf"]), "g": str(spec["gop"]),
                      "preset": "veryfast", "vsync": "passthrough"}
        ast = container.add_stream("aac", rate=SR)
        ast.format = "fltp"
        ast.layout = "mono"
        ast.time_base = Fraction(1, SR)

        event_ids = []
        for idx, local_t in enumerate(frame_times):
            arr, ev_id = draw_frame(spec, idx, local_t)
            event_ids.append(ev_id)
            vf = av.VideoFrame.from_ndarray(arr, format="rgb24")
            vf.pts = int(round(local_t * TIME_BASE))
            vf.time_base = Fraction(1, TIME_BASE)
            for pkt in vs.encode(vf):
                container.mux(pkt)

        # per-camera sine plus a short louder beep at each event this
        # camera actually covers (its local time is inside the clip)
        dur = frame_times[-1] + 0.1
        n = int(SR * dur)
        tt = np.arange(n) / SR
        wave = np.sin(2 * np.pi * spec["tone"] * tt) * 0.25
        for e in EVENTS:
            local_e = e["T"] - spec["offset"]
            if 0.0 <= local_e <= dur:
                m = (tt >= local_e) & (tt < local_e + 0.18)
                wave[m] += 0.45 * np.sin(2 * np.pi * 880 * tt[m])
        samples = np.clip(wave, -0.95, 0.95).astype("float32")
        chunk, pos = 1024, 0
        while pos < n:
            block = samples[pos:pos + chunk]
            af = av.AudioFrame.from_ndarray(
                block.reshape(1, -1), format="fltp", layout="mono")
            af.sample_rate = SR
            af.pts = pos
            for pkt in ast.encode(af):
                container.mux(pkt)
            pos += chunk
        for pkt in ast.encode():
            container.mux(pkt)
        for pkt in vs.encode():
            container.mux(pkt)
    finally:
        container.close()
    return event_ids


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ build
def build_package(pkg_dir):
    media_dir = os.path.join(pkg_dir, "media")
    os.makedirs(media_dir, exist_ok=True)
    rng = np.random.default_rng(SEED)

    gt = {"schema": "multicam-sync-ground-truth/1",
          "production_duration_s": DURATION,
          "time_base_ticks_per_s": TIME_BASE,
          "seed": SEED,
          "events": EVENTS,
          "cameras": [],
          "sources": {
              "builder": "tools/make_sync_media.py",
              "python": sys.version.split()[0],
              "av": av.__version__,
              "numpy": np.__version__,
              "pillow": Image.__version__,
          },
          "parameters": {"event_hold_ms": EVENT_HOLD_MS,
                         "frame_strip_bits": STRIP_BITS,
                         "event_strip_bits": EVENT_BITS,
                         "frame_size": [W, H], "audio_sr": SR}}

    streams_cfg = []
    for spec in CAMERAS:
        frame_times, gaps_local = schedule_camera(spec, rng)
        out_path = os.path.join(media_dir, f"{spec['name']}.mp4")
        print(f"[make_sync_media] {spec['name']}: {len(frame_times)} frames, "
              f"fps~{spec['fps']:g}, off={spec['offset']:+.2f}s, "
              f"gaps(T)={spec['gaps'] or '-'} variable={spec['variable']}")
        event_ids = build_clip(spec, frame_times, out_path)

        intervals = [round(frame_times[i + 1] - frame_times[i], 6)
                     for i in range(len(frame_times) - 1)]
        gt["cameras"].append({
            "name": spec["name"],
            "file": f"media/{spec['name']}.mp4",
            "sha256": sha256_of(out_path),
            "offset_s": spec["offset"],
            "nominal_fps": spec["fps"],
            "variable_fps": spec["variable"],
            "b_frames": spec["bf"],
            "local_coverage_s": list(spec["cover"]),
            "gaps_production_T": [list(g) for g in spec["gaps"]],
            "gaps_local_t": gaps_local,
            "n_frames": len(frame_times),
            "frame_local_times": frame_times,
            "frame_event_ids": event_ids,
            "frame_interval_s": {"min": min(intervals), "max": max(intervals),
                                 "uniform": bool(np.allclose(intervals, intervals[0]))},
            "tone_hz": spec["tone"],
        })
        streams_cfg.append({
            "name": spec["name"],
            "path": f"media/{spec['name']}.mp4",
            "offset": spec["offset"],
            "gaps": [list(g) for g in spec["gaps"]],
        })

    gt_path = os.path.join(pkg_dir, "ground_truth.json")
    with open(gt_path, "w") as fh:
        json.dump(gt, fh, indent=1)

    # strict project: every value the loader needs is explicit; no
    # stream may silently fall back to a default
    project = {
        "schema": "multicam-preview-project/2",
        "name": "sync-demo",
        "media_root": "media",
        "ground_truth": "ground_truth.json",
        "timeline_duration_s": DURATION,
        "streams": streams_cfg,
        "policy": "nearest",
        "reference": "virtual",
        "audio_source": "camA",
        "wait_budget_ms": 150,
        "speed": 1.0,
        "on_stall": "hold",
        "continue_others_on_stall": True,
        "gap_error_ms": 120.0,
        "simulate_decode_delay": {},
    }
    proj_path = os.path.join(pkg_dir, "project.json")
    with open(proj_path, "w") as fh:
        json.dump(project, fh, indent=1)
    print(f"[make_sync_media] wrote {gt_path} and {proj_path}")
    return proj_path, gt_path


def main():
    ap = argparse.ArgumentParser(description="build synchronised multicam material")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sync_demo"))
    args = ap.parse_args()
    build_package(args.out)


if __name__ == "__main__":
    main()
