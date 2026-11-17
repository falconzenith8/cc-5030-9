#!/usr/bin/env python3
"""Generate self-made synchronised multi-camera source material.

The pack is deliberately built to make synchronisation *auditable*:

  * every camera shares one master timeline T and a list of shared events
    (clapper flashes).  Each frame covering an event burns in the event id
    in every camera that is recording at that time;
  * cameras differ in fps, start offset, and frame timing.  One camera has
    non-uniform frame intervals (a clock drift); two cameras carry missing
    segments (recording gaps), one of them also starts late and ends early;
  * every frame is an individual PNG with a sidecar record giving its exact
    presentation time, raw pts, frame index, event tag and gap context;
  * sources.json records the generator, seed and every parameter so the
    pack is fully rebuildable; truth/ground_truth.json gives the expected
    nearest/hold picks at every audit time;
  * each camera gets an optional distinct sine tone (pure-stdlib WAV).

Run:  python3 -I tools/make_synced_media.py [output_dir] [--seed N]
"""
import argparse
import json
import math
import os
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multicam.imglib import Canvas, draw_text

W, H = 320, 240
STRIP_BITS, STRIP_H = 24, 8
SR = 44100
MASTER_DURATION = 12.0
TIME_BASE_DEN = 122880          # divides all frame times used here

# Shared events on the master timeline. "colour" is the flash colour and
# must stay identical across cameras — it is the visual common-event key.
EVENTS = [
    {"id": "E1", "t": 2.000, "label": "CLAP-1", "colour": [255, 80, 80]},
    {"id": "E2", "t": 4.000, "label": "CLAP-2", "colour": [80, 255, 120]},
    {"id": "E3", "t": 6.000, "label": "CLAP-3", "colour": [90, 150, 255]},
    {"id": "E4", "t": 8.200, "label": "CLAP-4", "colour": [255, 210, 70]},
    {"id": "E5", "t": 10.500, "label": "CLAP-5", "colour": [230, 110, 230]},
]
EVENT_WINDOW = 0.25             # flash banner stays visible +/- 0.25 s

# Camera definitions.
#   fps          nominal frame rate
#   offset       local_time = T - offset (negative => camera started early)
#   drift        per-frame time multiplier != 1 -> non-uniform intervals
#   jitter       deterministic pseudo-random per-frame time perturbation
#   start_t/end_t   master-time recording coverage (clipped timeline)
#   gaps         missing segments in MASTER time: no frames exist there
CAMERAS = [
    {
        "name": "camA", "fps": 30.0, "offset": 0.0, "drift": 1.0,
        "jitter": 0.0, "start_t": 0.0, "end_t": 11.6, "gaps": [],
        "bg": (28, 62, 122), "tone": 440.0,
    },
    {
        "name": "camB", "fps": 25.0, "offset": 0.35, "drift": 1.0,
        "jitter": 0.0, "start_t": 0.0, "end_t": 11.2,
        "gaps": [{"start": 5.0, "end": 6.8}],   # covers E3 (6.0) -> missing
        "bg": (122, 44, 44), "tone": 550.0,
    },
    {
        "name": "camC", "fps": 24.0, "offset": -0.8, "drift": 1.012,
        "jitter": 0.004, "start_t": 0.0, "end_t": 11.8,
        "gaps": [{"start": 7.4, "end": 7.9}],   # between E3 and E4
        "bg": (32, 110, 62), "tone": 660.0,
    },
    {
        "name": "camD", "fps": 15.0, "offset": 1.2, "drift": 1.0,
        "jitter": 0.0, "start_t": 1.2, "end_t": 9.5,
        "gaps": [{"start": 3.1, "end": 3.9}],   # late start, early end, gap
        "bg": (112, 92, 30), "tone": 330.0,
    },
]


def rng(seed, salt):
    """Deterministic LCG so rebuilds are bit-identical for a given seed."""
    state = (seed * 2654435761 + salt * 40503) & 0xFFFFFFFF
    while True:
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        yield (state >> 8) / 0x1000000       # 0..1


def event_at(t_master):
    for ev in EVENTS:
        if abs(t_master - ev["t"]) <= EVENT_WINDOW:
            return ev
    return None


def in_gap(t_master, gaps):
    return any(g["start"] <= t_master < g["end"] for g in gaps)


def frame_schedule(spec, seed):
    """Return (records, gap_segments) in camera LOCAL time.

    Frame i's ideal local time is i/fps; drift and jitter perturb it.
    Frames whose master time falls in a gap or outside the recording
    coverage are omitted — the missing segment is the absence of records.
    """
    fps, off = spec["fps"], spec["offset"]
    rand = rng(seed, sum(ord(c) for c in spec["name"]))
    nominal_n = int(math.ceil((spec["end_t"] - spec["start_t"]) * fps)) + 2
    raw = []
    for i in range(nominal_n):
        ideal = i / fps
        t_local = ideal * spec["drift"] + (next(rand) - 0.5) * 2 * spec["jitter"]
        t_master = t_local + off
        if t_master < spec["start_t"] or t_master >= spec["end_t"]:
            continue
        if in_gap(t_master, spec["gaps"]):
            continue
        raw.append((i, t_local, t_master))
    # build gap segments in local time and mark records bordering gaps
    gaps_local = [
        {"start_master": g["start"], "end_master": g["end"],
         "start_local": round(g["start"] - off, 6),
         "end_local": round(g["end"] - off, 6)}
        for g in spec["gaps"]
    ]
    records = []
    prev_index = None
    for i, t_local, t_master in raw:
        records.append({
            "frame_index": i,
            "time": round(t_local, 6),
            "time_master": round(t_master, 6),
            "missing_before": prev_index is not None and i != prev_index + 1,
        })
        prev_index = i
    # a record borders a gap when the next existing frame is not the next
    # frame index — the same evidence the decoder/kernel will see
    for k, rec in enumerate(records):
        rec["gap_after"] = (
            k + 1 < len(records)
            and records[k + 1]["frame_index"] != rec["frame_index"] + 1)
    return records, gaps_local


def draw_frame(spec, rec, event):
    img = Canvas(W, H, spec["bg"])
    n = rec["frame_index"]
    # moving white block — per-frame motion evidence shared by all cameras
    x = (n * 7) % (W - 48)
    img.fill_rect(x, 96, x + 48, 144, (225, 225, 225))
    draw_text(img, 8, 6, f"{spec['name']} F{n:05d}", (255, 255, 255), scale=2)
    draw_text(img, 8, 30, f"T{rec['time_master']:07.3f}", (255, 255, 150), scale=2)
    draw_text(img, 8, 52, f"L{rec['time']:07.3f} OFF{spec['offset']:+.2f}",
              (180, 220, 255), scale=1)
    draw_text(img, 8, 66, f"FPS{spec['fps']:g}", (180, 220, 255), scale=1)
    if rec.get("missing_before"):
        draw_text(img, W - 92, 6, "GAP-IN", (255, 120, 240), scale=2)
    if rec.get("gap_after"):
        draw_text(img, W - 100, 24, "GAP-OUT", (255, 120, 240), scale=2)
    if event is not None:
        # full-width colour band + event id: the common-event fingerprint
        img.fill_rect(0, 150, W - 1, 184, tuple(event["colour"]))
        draw_text(img, 10, 156, f"{event['label']} {event['id']} T{event['t']:.3f}",
                  (20, 20, 20), scale=3)
    # 24-bit frame-number strip (same convention as the legacy clips)
    for bit in range(STRIP_BITS):
        on = (n >> bit) & 1
        img.fill_rect(bit * 8, H - STRIP_H, bit * 8 + 7, H - 1,
                      (255, 255, 255) if on else (0, 0, 0))
    img.outline_rect(0, H - STRIP_H - 2, STRIP_BITS * 8 + 1, H - 1,
                     (255, 0, 0))
    return img


def write_wav(path, freq, dur_local):
    n = int(SR * dur_local)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        frames = bytearray()
        amp = int(0.3 * 32767)
        for i in range(n):
            v = int(amp * math.sin(2 * math.pi * freq * i / SR))
            frames += struct.pack("<h", v)
        wf.writeframes(bytes(frames))


def build_camera(spec, pack_dir, seed):
    cam_dir = os.path.join(pack_dir, "cameras", spec["name"])
    frames_dir = os.path.join(cam_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    records, gaps_local = frame_schedule(spec, seed)
    tb = TIME_BASE_DEN
    out_records = []
    for rec in records:
        ev = event_at(rec["time_master"])
        img = draw_frame(spec, rec, ev)
        fname = f"f_{rec['frame_index']:05d}.png"
        img.save(os.path.join(frames_dir, fname))
        pts = int(round(rec["time"] * tb))
        out_records.append({
            "file": fname,
            "frame_index": rec["frame_index"],
            "pts": pts,
            "time": rec["time"],
            "time_master": rec["time_master"],
            "pict": "I" if rec["frame_index"] == 0 or rec["missing_before"] else "P",
            "key_frame": rec["frame_index"] == 0 or rec["missing_before"],
            "event_id": ev["id"] if ev else None,
            "gap_after": rec["gap_after"],
            "missing_before": rec["missing_before"],
        })
    local_span = (records[-1]["time"] - records[0]["time"]) if records else 0.0
    write_wav(os.path.join(cam_dir, "audio.wav"), spec["tone"],
              max(0.1, local_span + 1.0 / spec["fps"]))
    meta = {
        "name": spec["name"],
        "fps": spec["fps"],
        "offset": spec["offset"],
        "width": W,
        "height": H,
        "time_base": [1, tb],
        "drift": spec["drift"],
        "jitter": spec["jitter"],
        "coverage_master": [spec["start_t"], spec["end_t"]],
        "gaps": gaps_local,
        "non_uniform": bool(spec["drift"] != 1.0 or spec["jitter"]),
        "tone_hz": spec["tone"],
        "frames": out_records,
    }
    with open(os.path.join(cam_dir, "camera.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return meta


def build_truth(pack_dir, metas):
    """Expected picks for every audit time (each shared event plus gap
    probes), for both policies.  This is the synchronisation oracle; the
    verifier recomputes picks through the real kernel and compares."""
    by_name = {m["name"]: m for m in metas}
    audit_times = sorted({ev["t"] for ev in EVENTS} |
                         {5.9, 6.1, 7.6, 3.5, 10.0, 11.0})

    def expected(name, T, policy):
        m = by_name[name]
        target = T - m["offset"]
        recs = m["frames"]
        if not recs or target < recs[0]["time"] - 1e-9:
            return {"state": "NOT_STARTED", "frame_index": None,
                    "event_id": None, "reason": "before first recorded frame"}
        le = [r for r in recs if r["time"] <= target + 1e-9]
        beyond = next((r for r in recs if r["time"] > target + 1e-9), None)
        if policy == "hold":
            chosen = le[-1]
        else:
            chosen = le[-1] if beyond is None else min(
                (le[-1], beyond), key=lambda r: abs(r["time"] - target))
        last = recs[-1]
        span = (recs[-1]["time"] - recs[-2]["time"]) if len(recs) > 1 else 1.0 / m["fps"]
        cover = span if policy == "hold" else span / 2.0
        if target > last["time"] + cover:
            return {"state": "ENDED", "frame_index": last["frame_index"],
                    "event_id": last["event_id"], "reason": "past last frame"}
        # gap evidence: nearest recorded frames straddle a missing segment
        gap = None
        for g in m["gaps"]:
            if g["start_local"] <= target < g["end_local"]:
                gap = [g["start_local"], g["end_local"]]
        state = "OK"
        if chosen.get("gap_after") and target > chosen["time"]:
            nxt = next((r for r in recs if r["time"] > target + 1e-9), None)
            if nxt is None or abs(chosen["time"] - target) <= abs(nxt["time"] - target):
                state = "GAP"
        return {"state": state, "frame_index": chosen["frame_index"],
                "pts": chosen["pts"], "pts_time": chosen["time"],
                "event_id": chosen["event_id"],
                "target_local": round(target, 6),
                "err_ms": round((chosen["time"] - target) * 1000, 3),
                "inside_gap": gap}

    truth = {"audit_times": audit_times, "policies": ["nearest", "hold"],
             "events": EVENTS, "expected": {}}
    for T in audit_times:
        truth["expected"][f"{T:.3f}"] = {
            name: {pol: expected(name, T, pol) for pol in ("nearest", "hold")}
            for name in by_name}
    with open(os.path.join(pack_dir, "truth", "ground_truth.json"), "w",
              encoding="utf-8") as fh:
        json.dump(truth, fh, indent=1)
    with open(os.path.join(pack_dir, "truth", "events.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"events": EVENTS, "window_s": EVENT_WINDOW,
                   "master_duration_s": MASTER_DURATION}, fh, indent=1)
    return truth


def build_pack(out_dir, seed=20261117):
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "cameras"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "truth"), exist_ok=True)
    metas = [build_camera(spec, out_dir, seed) for spec in CAMERAS]
    build_truth(out_dir, metas)

    project = {
        "package": "multicam-synced-pack",
        "version": 1,
        "master_duration_s": MASTER_DURATION,
        "reference": "virtual",
        "reference_options": ["virtual"] + [s["name"] for s in CAMERAS],
        "policy": "nearest",
        "wait_budget_ms": 150,
        "on_stall": "hold",
        "continue_others_on_stall": True,
        "speed": 1.0,
        "audio_source": "camA",
        "streams": [
            {"name": s["name"],
             "path": os.path.join("cameras", s["name"]),
             "offset": s["offset"]}
            for s in CAMERAS],
        "truth": "truth/ground_truth.json",
        "events": "truth/events.json",
    }
    with open(os.path.join(out_dir, "project.json"), "w", encoding="utf-8") as fh:
        json.dump(project, fh, indent=1)

    sources = {
        "generator": "tools/make_synced_media.py",
        "seed": seed,
        "python": sys.version.split()[0],
        "third_party": [],
        "parameters": {
            "width": W, "height": H, "master_duration_s": MASTER_DURATION,
            "event_window_s": EVENT_WINDOW, "time_base_den": TIME_BASE_DEN,
            "audio": {"sample_rate": SR, "format": "wav_s16le_mono"},
            "cameras": CAMERAS,
            "events": EVENTS,
        },
        "frame_format": "png rgb8, one file per recorded frame",
    }
    with open(os.path.join(out_dir, "sources.json"), "w", encoding="utf-8") as fh:
        json.dump(sources, fh, indent=1)
    return out_dir


def main():
    ap = argparse.ArgumentParser(description="build synchronised camera pack")
    ap.add_argument("out_dir", nargs="?",
                    default=os.path.join(os.path.dirname(
                        os.path.dirname(os.path.abspath(__file__))),
                        "demo_pack"))
    ap.add_argument("--seed", type=int, default=20261117)
    args = ap.parse_args()
    path = build_pack(args.out_dir, args.seed)
    print(f"[make_synced_media] pack written to {path}")
    for spec in CAMERAS:
        print(f"  {spec['name']}: fps={spec['fps']:g} offset={spec['offset']:+.2f}"
              f" drift={spec['drift']} gaps={len(spec['gaps'])}")


if __name__ == "__main__":
    main()
