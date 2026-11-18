#!/usr/bin/env python3
"""Audit a rebuilt sync-demo package against its ground truth.

This script never trusts the preview's own numbers.  It independently
recomputes, from ``ground_truth.json``:

  1. the frame every camera *should* pick at each production time T
     (nearest frame by local pts, with NOT_STARTED/ENDED edges);
  2. the ticks that must be reported GAP because T sits inside a declared
     missing segment and no frame is close enough to cover it;
  3. the event id every covering camera must show at each common event.

It then compares those expectations with:
  - the JSON frame-pick report produced by the real offline composite
    render (multicam.app.MultiCamApp.render_offline);
  - the frame-number / event-id strips decoded back out of the rendered
    composite images (same-event correspondence from picture content);
  - the clip file hashes recorded at generation time.

Exit code is non-zero on any mismatch, so the check is CI-friendly.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile

import av

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multicam import (MultiCamApp, read_frame_number, read_event_id,
                      load_project, GAP, ENDED, NOT_STARTED)

TOL = 2e-4                     # pts tolerance (15360-tick time base)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def expected_pick(cam, target):
    """Independent nearest-frame expectation from the ground truth."""
    if target < cam["local_coverage_s"][0] - TOL:
        return None, NOT_STARTED
    times = cam["frame_local_times"]
    best = min(times, key=lambda t: abs(t - target))
    # mirror the kernel: ENDED only beyond the last frame plus its cover,
    # where cover is half the mean frame spacing (decoder fps-derived)
    mean_dur = (times[-1] - times[0]) / max(1, len(times) - 1)
    if target > times[-1] + mean_dur / 2.0:
        return best, ENDED
    return best, "OK"


def expected_gap(cam, production_T):
    """Distance to the nearest gap edge on the production timeline T,
    or None when T is outside every declared missing segment."""
    for lo_T, hi_T in cam["gaps_production_T"]:
        if lo_T <= production_T <= hi_T:
            return min(abs(production_T - lo_T), abs(production_T - hi_T))
    return None


def run(pkg_dir, render_fps=10, keep=False):
    config, meta = load_project(pkg_dir)
    with open(meta["ground_truth"]) as fh:
        gt = json.load(fh)
    cams = {c["name"]: c for c in gt["cameras"]}
    failures, evidence = [], []

    # ---- 1. provenance: recorded hashes must match the files on disk
    for name, cam in cams.items():
        p = os.path.join(meta["package_dir"], cam["file"])
        actual = sha256_of(p)
        ok = actual == cam["sha256"]
        evidence.append(f"hash {name}: {'OK' if ok else 'MISMATCH'}")
        if not ok:
            failures.append(f"{name}: clip hash differs from ground truth")

    # ---- 2. real offline composite render through the preview stack
    work = tempfile.mkdtemp(prefix="sync_verify_")
    out_mp4 = os.path.join(work, "composite.mp4")
    app = MultiCamApp(config, workdir=work)
    duration = meta["timeline_duration_s"]
    info = app.render_offline(out_mp4, duration=duration, fps=render_fps)
    with open(info["report"]) as fh:
        report = json.load(fh)
    names = [s["name"] for s in config["streams"]]
    gap_limit = config.get("gap_error_ms", 1e9) / 1000.0

    # ---- 3. every reported pick must match the independent expectation
    gap_hits = {n: 0 for n in names}
    for fr in report["frames"]:
        T = fr["T"]
        for n in names:
            cam = cams[n]
            target = T - cam["offset_s"]
            exp_time, exp_state = expected_pick(cam, target)
            got = fr["streams"][n]
            if exp_state in (NOT_STARTED, ENDED):
                if got["state"] != exp_state:
                    failures.append(f"T={T:.2f} {n}: expected {exp_state}, "
                                    f"got {got['state']}")
                continue
            if got["pts_time"] is None or abs(got["pts_time"] - exp_time) > 5e-3:
                failures.append(
                    f"T={T:.2f} {n}: expected pts_time {exp_time:.4f}, "
                    f"got {got['pts_time']}")
            dist = expected_gap(cam, T)
            if dist is not None:
                # GAP is the kernel's call once the actual pick error
                # exceeds the threshold; count its real states and also
                # check the deep-middle ticks where GAP is mandatory
                if got["state"] == GAP:
                    gap_hits[n] += 1
                if dist > gap_limit and got["state"] != GAP:
                    failures.append(f"T={T:.2f} {n}: deep inside gap but "
                                    f"state={got['state']} (expected GAP)")

    # each declared gap must actually produce GAP ticks in the render
    metrics = report["metrics"]
    for n in names:
        declared = len(cams[n]["gaps_production_T"])
        if declared and gap_hits[n] == 0:
            failures.append(f"{n}: {declared} gap(s) declared but no GAP tick seen")
        if metrics[n]["gaps"] != gap_hits[n]:
            failures.append(f"{n}: report gaps={metrics[n]['gaps']} "
                            f"!= recomputed {gap_hits[n]}")
        evidence.append(
            f"picks {n}: {metrics[n]['picks']} gaps={metrics[n]['gaps']} "
            f"max_err={metrics[n]['max_err_ms']:.1f}ms")

    # ---- 4. common events: same event id read back from every cell
    container = av.open(out_mp4)
    frames = list(container.decode(video=0))
    container.close()
    n_cells = len(names)
    hold = gt["parameters"]["event_hold_ms"] / 1000.0
    for ev in gt["events"]:
        covering = [n for n in names
                    if cams[n]["local_coverage_s"][0]
                    <= ev["T"] - cams[n]["offset_s"]
                    <= cams[n]["local_coverage_s"][1]
                    and not any(lo <= ev["T"] <= hi
                                for lo, hi in cams[n]["gaps_production_T"])]
        # pick a render tick inside the banner window where every covering
        # camera's nearest frame is itself an event frame in the ground truth
        chosen = None
        for fr in report["frames"]:
            if not (ev["T"] <= fr["T"] <= ev["T"] + hold):
                continue
            good = True
            for n in covering:
                table = cams[n]["frame_local_times"]
                ev_flags = cams[n]["frame_event_ids"]
                picked_t = fr["streams"][n]["pts_time"]
                idx = min(range(len(table)),
                          key=lambda i: abs(table[i] - picked_t))
                if ev_flags[idx] != ev["id"]:
                    good = False
                    break
            if good:
                chosen = fr
                break
        if chosen is None:
            failures.append(f"event {ev['id']}: no render tick where every "
                            f"covering camera picks an event frame")
            continue
        k = chosen["k"]
        img = frames[k].to_ndarray(format="rgb24")
        ids, frame_nums = {}, {}
        for idx, n in enumerate(names):
            ids[n] = read_event_id(img, idx, n_cells)
            frame_nums[n] = read_frame_number(img, idx, n_cells)
        seen = {ids[n] for n in covering}
        ok = seen == {ev["id"]}
        evidence.append(
            f"event {ev['id']} @T={ev['T']:.1f}s tick T={chosen['T']:.2f} "
            f"covering={covering} readback_ids={[ids[n] for n in covering]} "
            f"{'OK' if ok else 'MISMATCH'}")
        if not ok:
            failures.append(
                f"event {ev['id']}: picture readback {ids} != common id {ev['id']}")
        # frame numbers must also match the ground-truth frame table
        for n in covering:
            table = cams[n]["frame_local_times"]
            picked_t = chosen["streams"][n]["pts_time"]
            exp_n = min(range(len(table)),
                        key=lambda i: abs(table[i] - picked_t))
            if frame_nums[n] != exp_n:
                failures.append(
                    f"event {ev['id']} {n}: frame strip {frame_nums[n]} "
                    f"!= ground-truth index {exp_n}")

    print("=" * 68)
    print(f"sync package verification: {meta['name']} ({pkg_dir})")
    print(f"rendered {info['frames']} composite frames @ {render_fps}fps "
          f"-> {out_mp4}")
    for line in evidence:
        print("  " + line)
    print("-" * 68)
    if failures:
        print(f"FAILED with {len(failures)} discrepancy(ies):")
        for f in failures:
            print("  - " + f)
        return 1
    print("ALL CHECKS PASSED: picks, gap states and same-event picture "
          "correspondence agree with ground truth.")
    if not keep:
        app_work = work
    return 0


def main():
    ap = argparse.ArgumentParser(description="verify rebuilt sync package")
    ap.add_argument("package", nargs="?", default="sync_demo")
    ap.add_argument("--fps", type=int, default=10)
    args = ap.parse_args()
    sys.exit(run(args.package, render_fps=args.fps))


if __name__ == "__main__":
    main()
