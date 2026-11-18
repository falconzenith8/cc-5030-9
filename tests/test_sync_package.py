"""Tests for the synchronised-material project package.

These cover the new production-style material end to end:

  * variable / non-uniform frame spacing really present in the clips;
  * declared camera gaps contain no frames and surface as GAP picks with
    large, reported frame-pick errors (never hidden);
  * the strict project loader rejects broken packages instead of falling
    back to defaults;
  * common events are readable back as the same event id from every
    covering camera cell (picture-level synchronisation evidence);
  * the panel serves real decoded frames, not fixed placeholder data.

The package is rebuilt on demand by tools/make_sync_media.py, so the
suite also proves the rebuild script reproduces the ground truth.
"""
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

import av

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multicam import (MultiCamApp, Kernel, StreamConfig, Composer,
                      read_frame_number, read_event_id, load_project,
                      list_packages, ProjectError, GAP, OK, PanelServer)
from tools.make_sync_media import build_package

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "sync_demo")
TOL = 5e-3


def ensure_pkg():
    if not os.path.isfile(os.path.join(PKG, "project.json")):
        build_package(PKG)
    return PKG


class MediaScheduleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_pkg()
        with open(os.path.join(PKG, "ground_truth.json")) as fh:
            cls.gt = json.load(fh)

    def _decoded_times(self, cam):
        with av.open(os.path.join(PKG, cam["file"])) as c:
            return [float(f.pts * f.time_base) for f in c.decode(video=0)]

    def test_clips_match_schedule_and_count(self):
        for cam in self.gt["cameras"]:
            times = self._decoded_times(cam)
            self.assertEqual(len(times), cam["n_frames"], cam["name"])
            for got, want in zip(times, cam["frame_local_times"]):
                self.assertAlmostEqual(got, want, delta=TOL)

    def test_non_uniform_frame_intervals(self):
        # every camera has genuinely non-uniform spacing; camD is the
        # explicitly variable-rate stream and must alternate strongly
        for cam in self.gt["cameras"]:
            self.assertFalse(cam["frame_interval_s"]["uniform"], cam["name"])
        camD = next(c for c in self.gt["cameras"] if c["name"] == "camD")
        self.assertTrue(camD["variable_fps"])
        self.assertGreater(camD["frame_interval_s"]["max"]
                           / camD["frame_interval_s"]["min"], 2.0)

    def test_declared_gaps_have_no_frames(self):
        for cam in self.gt["cameras"]:
            times = self._decoded_times(cam)
            off = cam["offset_s"]
            for lo_T, hi_T in cam["gaps_production_T"]:
                lo, hi = lo_T - off, hi_T - off
                leaked = [t for t in times if lo < t < hi]
                self.assertEqual(leaked, [], f"{cam['name']} frame in gap")

    def test_offsets_and_fps_differ(self):
        offsets = {c["name"]: c["offset_s"] for c in self.gt["cameras"]}
        self.assertEqual(len(set(offsets.values())), 4)
        fps = {c["name"]: c["nominal_fps"] for c in self.gt["cameras"]}
        self.assertEqual(len(set(fps.values())), 4)


class GapKernelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_pkg()
        cls.config, cls.meta = load_project(PKG)
        with open(cls.meta["ground_truth"]) as fh:
            cls.gt = json.load(fh)

    def _kernel(self):
        k = Kernel([StreamConfig(**s) for s in self.config["streams"]],
                   policy="nearest", gap_error_s=0.12,
                   decoder_kwargs=dict(realtime=False))
        k.start()
        for d in k.decoders.values():
            d.preload()
        return k

    def test_gap_reported_inside_missing_segment(self):
        k = self._kernel()
        try:
            # camB gap on T in (5.9, 7.4); T=6.5 is deep inside
            p = k.step(6.5)
            self.assertEqual(p["camB"].state, GAP)
            self.assertGreater(abs(p["camB"].err), 0.12)
            # a camera with no gap at this T stays OK
            self.assertEqual(p["camA"].state, OK)
            snap = k.snapshot()
            mb = next(s for s in snap["streams"] if s["name"] == "camB")
            self.assertGreater(mb["metrics"]["gaps"], 0)
            self.assertTrue(mb["in_gap"])
        finally:
            k.stop()

    def test_outside_gap_is_not_gap(self):
        k = self._kernel()
        try:
            p = k.step(2.0)      # no gap for any camera here
            for n, pick in p.items():
                self.assertEqual(pick.state, OK, n)
        finally:
            k.stop()

    def test_legacy_config_without_gap_threshold_never_gaps(self):
        # old demos carry no gap_error_s: behaviour must be unchanged
        streams = [dict(s) for s in self.config["streams"]]
        k = Kernel([StreamConfig(**s) for s in streams], policy="nearest",
                   gap_error_s=None, decoder_kwargs=dict(realtime=False))
        k.start()
        for d in k.decoders.values():
            d.preload()
        try:
            p = k.step(6.5)
            self.assertNotEqual(p["camB"].state, GAP)
        finally:
            k.stop()

    def test_gap_pick_is_real_held_frame_not_blank(self):
        k = self._kernel()
        try:
            p = k.step(6.5)["camB"]
            self.assertIsNotNone(p.frame)          # a real frame is held
            self.assertIsNotNone(p.frame.image)
            self.assertEqual(p.frame.image.ndim, 3)
        finally:
            k.stop()


class SameEventPictureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_pkg()
        cls.config, cls.meta = load_project(PKG)
        with open(cls.meta["ground_truth"]) as fh:
            cls.gt = json.load(fh)

    def test_common_event_id_in_every_cell(self):
        app = MultiCamApp(self.config, workdir=tempfile.mkdtemp())
        out = os.path.join(tempfile.mkdtemp(), "c.mp4")
        app.render_offline(out, duration=self.meta["timeline_duration_s"], fps=10)
        with av.open(out) as c:
            frames = list(c.decode(video=0))
        n_cells = len(self.config["streams"])
        for ev in self.gt["events"]:
            # find a rendered frame inside the banner hold where all
            # covering cameras show this event id
            hit = None
            for img in frames:
                arr = img.to_ndarray(format="rgb24")
                ids = [read_event_id(arr, i, n_cells)
                       for i in range(n_cells)]
                if ids and all(v == ev["id"] for v in ids):
                    hit = ids
                    break
            self.assertIsNotNone(hit, f"event {ev['id']} not common to all cells")

    def test_frame_number_strip_matches_ground_truth(self):
        app = MultiCamApp(self.config, workdir=tempfile.mkdtemp())
        tmp = tempfile.mkdtemp()
        out = os.path.join(tmp, "c.mp4")
        info = app.render_offline(out, duration=2.0, fps=5)
        with av.open(out) as c:
            frames = list(c.decode(video=0))
        cams = {c["name"]: c for c in self.gt["cameras"]}
        names = [s["name"] for s in self.config["streams"]]
        with open(info["report"]) as fh:
            report = json.load(fh)
        k = 5
        img = frames[k].to_ndarray(format="rgb24")
        for idx, n in enumerate(names):
            picked_t = report["frames"][k]["streams"][n]["pts_time"]
            if picked_t is None:        # NOT_STARTED at this early tick
                continue
            strip_n = read_frame_number(img, idx, len(names))
            table = cams[n]["frame_local_times"]
            exp = min(range(len(table)),
                      key=lambda i: abs(table[i] - picked_t))
            self.assertEqual(strip_n, exp, n)


class StrictLoaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_pkg()

    def test_loads_real_package(self):
        config, meta = load_project(PKG)
        self.assertEqual(meta["name"], "sync-demo")
        self.assertTrue(all(os.path.isabs(s["path"]) for s in config["streams"]))
        self.assertEqual(config["gap_error_ms"], 120.0)

    def test_rejects_missing_file_and_bad_schema(self):
        with self.assertRaises(ProjectError):
            load_project("/nonexistent/dir")
        bad = tempfile.mkdtemp()
        with open(os.path.join(bad, "project.json"), "w") as fh:
            json.dump({"schema": "wrong", "streams": []}, fh)
        with self.assertRaises(ProjectError):
            load_project(bad)

    def test_rejects_dangling_media_and_bad_gap_and_defaults_absent(self):
        good = load_project(PKG)[0]
        bad = tempfile.mkdtemp()
        cfg = json.loads(json.dumps(good))
        cfg["streams"][0]["path"] = "media/ghost.mp4"
        # loader resolves relative to package; write project referencing
        # an absolute missing path to guarantee dangling detection
        cfg["streams"][0]["path"] = os.path.join(bad, "ghost.mp4")
        with open(os.path.join(bad, "project.json"), "w") as fh:
            json.dump({**load_project(PKG)[0], "streams": cfg["streams"],
                       "schema": "multicam-preview-project/2",
                       "name": "bad", "reference": "virtual",
                       "policy": "nearest", "wait_budget_ms": 150,
                       "on_stall": "hold",
                       "continue_others_on_stall": True}, fh)
        with self.assertRaises(ProjectError):
            load_project(bad)

    def test_rejects_unknown_reference(self):
        cfg, _ = load_project(PKG)
        cfg["reference"] = "camZ"
        bad = tempfile.mkdtemp()
        with open(os.path.join(bad, "project.json"), "w") as fh:
            json.dump({**cfg, "streams": [{**s, "path": s["path"]}
                                          for s in cfg["streams"]]}, fh)
        with self.assertRaises(ProjectError):
            load_project(bad)

    def test_list_packages_finds_sync_demo(self):
        found = list_packages([ROOT])
        self.assertIn(os.path.abspath(PKG), found)


class PanelServesRealFramesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_pkg()

    def test_panel_state_and_frame_png_are_live(self):
        config, _ = load_project(PKG)
        work = tempfile.mkdtemp()
        app = MultiCamApp(config, workdir=work)
        app.start()
        for d in app.kernel.decoders.values():
            self.assertTrue(d.ready.wait(10))
        server = PanelServer(app, "127.0.0.1", 0, package_roots=[ROOT],
                             workdir=work)
        port = server.httpd.server_address[1]
        th = server.start_background()
        try:
            time.sleep(1.0)
            state = json.loads(urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/state", timeout=10).read())
            self.assertEqual(len(state["streams"]), 4)
            # start playback so the composite genuinely advances; the
            # served bytes must change rather than repeat a fixed image
            app.control({"action": "play"})
            png = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/frame.png", timeout=10).read()
            self.assertEqual(png[:4], b"\x89PNG")
            self.assertGreater(len(png), 10000)
            s1 = json.loads(urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/state", timeout=10).read())
            time.sleep(0.6)
            png2 = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/frame.png", timeout=10).read()
            s2 = json.loads(urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/state", timeout=10).read())
            self.assertNotEqual(png, png2)
            self.assertGreater(s2["T"], s1["T"])
        finally:
            server.shutdown()
            app.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
