#!/usr/bin/env python3
"""Verify synchronised picks against the ground-truth oracle and emit
executable evidence.

For every audit time and both policies this tool:
  1. runs the REAL kernel on the REAL package decoders (preloaded),
  2. compares state/frame/event with truth/ground_truth.json,
  3. renders a composite image and reads the burned-in frame-number strip
     back from each cell, proving the displayed frame matches the pick,
  4. records frame-timing differences (target vs selected pts per camera)
     so multi-camera frame-pick divergence is measured, not assumed.

Shared events get dedicated evidence images: all cameras that are
recording at that master time must show the same event id; a camera
inside a missing segment must visibly show its gap/state instead.

Outputs land in <pack>/exports/verify/:
  verdict.json              machine-readable pass/fail per check
  event_<id>.png            one composite per shared event
  audit_<T>_<policy>.png    composites at each audit time
  evidence.md               human-readable summary with image references
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multicam.app import build_cell_view
from multicam.compose import Composer, read_frame_number
from multicam.imglib import write_png
from multicam.kernel import Kernel, StreamConfig

from multicam.package import CameraPackage, load_events, load_project, load_sources


def build_kernel(pack_dir, policy):
    cfg = load_project(pack_dir)
    streams = []
    for s in cfg["streams"]:
        path = s["path"]
        if not os.path.isabs(path):
            path = os.path.join(pack_dir, path)
        streams.append(StreamConfig(name=s["name"], path=path,
                                    offset=float(s["offset"])))
    k = Kernel(streams, policy=policy, wait_budget=5.0,
               decoder_kwargs=dict(realtime=False))
    k.start()
    for dec in k.decoders.values():
        dec.preload()
    return k, cfg


def run(pack_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(pack_dir, "truth", "ground_truth.json"),
              encoding="utf-8") as fh:
        truth = json.load(fh)
    events = load_events(pack_dir)["events"]
    sources = load_sources(pack_dir)
    verdict = {"pack": os.path.abspath(pack_dir), "seed": sources["seed"],
               "checks": [], "passed": 0, "failed": 0,
               "event_correspondence": [], "frame_pick_divergence": []}
    names = [s["name"] for s in load_project(pack_dir)["streams"]]

    def record(ok, desc, detail):
        verdict["checks"].append({"ok": ok, "desc": desc, "detail": detail})
        verdict["passed" if ok else "failed"] += 1

    for policy in truth["policies"]:
        kernel, cfg = build_kernel(pack_dir, policy)
        composer = Composer(len(names))
        try:
            for T in truth["audit_times"]:
                key = f"{T:.3f}"
                picks = kernel.step(float(T))
                cells = [build_cell_view(kernel, kernel.streams[n], picks[n])
                         for n in names]
                img = composer.render(cells)
                img_path = os.path.join(out_dir, f"audit_{key}_{policy}.png")
                write_png(img_path, composer.width, composer.height, img.buf)
                errs = {}
                for idx, name in enumerate(names):
                    exp = truth["expected"][key][name][policy]
                    got = picks[name]
                    # 1) state/frame must match the oracle
                    state_ok = got.state == exp["state"]
                    fi = got.frame.frame_index if got.frame else None
                    frame_ok = fi == exp["frame_index"]
                    ev = got.frame.event_id if got.frame else None
                    event_ok = ev == exp["event_id"]
                    record(state_ok, f"{policy} T={key} {name} state",
                           {"expected": exp["state"], "got": got.state})
                    record(frame_ok, f"{policy} T={key} {name} frame",
                           {"expected": exp["frame_index"], "got": fi})
                    record(event_ok, f"{policy} T={key} {name} event tag",
                           {"expected": exp["event_id"], "got": ev})
                    # 2) burned-in strip readback must equal the picked frame
                    if got.frame is not None:
                        readback = read_frame_number(img, idx, len(names))
                        record(readback == fi,
                               f"{policy} T={key} {name} strip readback",
                               {"picked": fi, "readback": readback})
                    if got.frame is not None:
                        errs[name] = round(got.err * 1000.0, 3)
                if errs:
                    spread = round(max(errs.values()) - min(errs.values()), 3)
                    verdict["frame_pick_divergence"].append(
                        {"T": float(T), "policy": policy,
                         "err_ms_by_camera": errs, "spread_ms": spread})
        finally:
            kernel.stop()

    # ---- shared-event correspondence: event id identical across cameras
    # that are recording; gap cameras must show no event and report context
    kernel, cfg = build_kernel(pack_dir, "nearest")
    composer = Composer(len(names))
    try:
        for ev in events:
            T = ev["t"]
            picks = kernel.step(float(T))
            cells = [build_cell_view(kernel, kernel.streams[n], picks[n])
                     for n in names]
            img = composer.render(cells)
            img_path = os.path.join(out_dir, f"event_{ev['id']}.png")
            write_png(img_path, composer.width, composer.height, img.buf)
            row = {"event": ev["id"], "T": T, "image": os.path.basename(img_path),
                   "cameras": {}}
            shown = set()
            for idx, name in enumerate(names):
                pick = picks[name]
                rec = {"state": pick.state,
                       "event_id": pick.frame.event_id if pick.frame else None,
                       "frame_index": pick.frame.frame_index if pick.frame else None,
                       "err_ms": round(pick.err * 1000.0, 3) if pick.frame else None}
                row["cameras"][name] = rec
                if rec["event_id"] == ev["id"]:
                    shown.add(name)
                    # colour band fingerprint check: sample the band pixels
                    rgb = pick.frame.image
                    band_ok = _band_matches(rgb, ev["colour"])
                    record(band_ok, f"event {ev['id']} {name} colour band",
                           {"expected": ev["colour"], "band_present": band_ok})
                else:
                    # camera must be in a declared missing segment, not
                    # started or ended — never silently showing another event
                    exp_here = truth["expected"][f"{T:.3f}"][name]["nearest"]
                    excused = bool(exp_here.get("inside_gap")) or \
                        pick.state in ("NOT_STARTED", "ENDED", "STALLED", "GAP")
                    record(excused,
                           f"event {ev['id']} {name} missing-segment context",
                           {"state": pick.state,
                            "inside_gap": exp_here.get("inside_gap")})
            record(len(shown) >= 2,
                   f"event {ev['id']} visible on >=2 cameras",
                   {"cameras_showing": sorted(shown)})
            verdict["event_correspondence"].append(row)
    finally:
        kernel.stop()

    # ---- gap presence is real: every declared gap has no frame records
    for name in names:
        cam = CameraPackage(os.path.join(pack_dir, "cameras", name))
        for g in cam.gaps:
            inside = [r for r in cam.frames
                      if g["start_local"] <= r["time"] < g["end_local"]]
            record(not inside, f"{name} gap {g['start_local']:.2f}-"
                               f"{g['end_local']:.2f} has no frames",
                   {"frames_inside": len(inside)})
        record(cam.fps > 0 and len(cam.frames) > 0,
               f"{name} package has recorded frames",
               {"frames": len(cam.frames), "fps": cam.fps})

    verdict["ok"] = verdict["failed"] == 0
    with open(os.path.join(out_dir, "verdict.json"), "w",
              encoding="utf-8") as fh:
        json.dump(verdict, fh, indent=1)
    _write_markdown(out_dir, verdict)
    return verdict


def _band_matches(rgb, colour):
    """The event band is a full-width strip at source y=150..184. Text is
    drawn in its middle, so sample the band's top and bottom edges where
    only the background colour can be present."""
    w = 320
    target = tuple(colour)
    ok = 0
    total = 0
    for y in (153, 181):
        for x in (12, 70, 140, 210, 280, 308):
            total += 1
            i = (y * w + x) * 3
            px = tuple(rgb[i:i + 3])
            if all(abs(int(px[c]) - target[c]) <= 12 for c in range(3)):
                ok += 1
    return ok >= total - 1


def _write_markdown(out_dir, verdict):
    lines = ["# 同步核验证据 / sync verification evidence", "",
             f"pack: `{verdict['pack']}`",
             f"seed: `{verdict['seed']}`",
             f"result: **{'PASS' if verdict['ok'] else 'FAIL'}** "
             f"({verdict['passed']} passed, {verdict['failed']} failed)", "",
             "## 共同事件画面对应 / shared-event correspondence", ""]
    for row in verdict["event_correspondence"]:
        lines.append(f"### {row['event']} @ T={row['T']:.3f}s — "
                     f"`{row['image']}`")
        lines.append("")
        lines.append("| 机位 | 状态 | 事件 | 帧号 | 误差ms |")
        lines.append("|---|---|---|---|---|")
        for name, c in row["cameras"].items():
            lines.append(f"| {name} | {c['state']} | {c['event_id'] or '-'} | "
                         f"{c['frame_index'] if c['frame_index'] is not None else '-'} | "
                         f"{c['err_ms'] if c['err_ms'] is not None else '-'} |")
        lines.append("")
    lines.append("## 取帧差异 / frame-pick divergence (ms)")
    lines.append("")
    lines.append("| T | policy | spread_ms | per-camera err_ms |")
    lines.append("|---|---|---|---|")
    for d in verdict["frame_pick_divergence"]:
        lines.append(f"| {d['T']:.3f} | {d['policy']} | {d['spread_ms']} | "
                     f"{json.dumps(d['err_ms_by_camera'])} |")
    lines.append("")
    lines.append("## 检查明细 / checks")
    lines.append("")
    for c in verdict["checks"]:
        lines.append(f"- [{'x' if c['ok'] else ' '}] {c['desc']} "
                     f"`{json.dumps(c['detail'], ensure_ascii=False)}`")
    with open(os.path.join(out_dir, "evidence.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description="verify synchronised media pack")
    ap.add_argument("pack_dir", nargs="?", default="demo_pack")
    ap.add_argument("--out", help="evidence output directory")
    args = ap.parse_args()
    out = args.out or os.path.join(args.pack_dir, "exports", "verify")
    verdict = run(args.pack_dir, out)
    print(f"[verify] {'PASS' if verdict['ok'] else 'FAIL'} "
          f"{verdict['passed']} passed / {verdict['failed']} failed")
    print(f"[verify] evidence -> {out}")
    sys.exit(0 if verdict["ok"] else 1)


if __name__ == "__main__":
    main()
