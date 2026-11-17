"""Kernel and end-to-end tests for the multi-camera sync preview.

Backend-agnostic: the legacy sample set is built as mp4 clips when the
optional PyAV/numpy/ffmpeg stack exists, and as stdlib PNG camera packages
otherwise.  Covers per-stream time bases, decode order vs presentation
selection, nearest/hold policies across different fps, early-ending clips,
negative start offsets, bounded wait on slow decoders (with the
continue-others configuration both ways), single-source audio monitoring,
missing segments, and frame-number read-back from the real composite.
"""
import json
import os
import sys
import tempfile
import unittest
from fractions import Fraction
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multicam import (Kernel, StreamConfig, MultiCamApp, Composer,
                      read_frame_number, OK, STALL, ENDED, NOT_STARTED,
                      HELD, GAP, make_decoder)
from multicam.app import build_cell_view
from multicam.media import _HAS_AV
from tools.make_media import ensure_media, TB_DEN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "media_legacy")


def cam(name):
    return os.path.join(MEDIA, name)


def make_kernel(specs, **kw):
    cfgs = [StreamConfig(name=n, path=cam(n), offset=o) for n, o in specs]
    k = Kernel(cfgs, decoder_kwargs=dict(realtime=False), **kw)
    k.start()
    for d in k.decoders.values():
        d.preload()
    return k


def frame_num(pick, fps):
    return int(round(pick.frame.time * fps))


class KernelTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_media(MEDIA)
        cls.has_av = _HAS_AV


class TestTimeBaseAndDecodeOrder(KernelTestBase):
    def test_streams_keep_own_time_base(self):
        k = make_kernel([("camA", 0.0), ("camC", 0.0)])
        try:
            tbA = k.decoders["camA"].time_base
            tbC = k.decoders["camC"].time_base
            if self.has_av:
                # mp4 muxing assigns stream-specific codec time bases
                self.assertEqual(tbA, Fraction(1, 15360))
                self.assertEqual(tbC, Fraction(1, 12288))
            else:
                self.assertEqual(tbA, Fraction(1, TB_DEN))
                self.assertEqual(tbC, Fraction(1, TB_DEN))
            self.assertIsNotNone(tbA)
            k.step(0.5)
            snap = k.snapshot()
            by_name = {s["name"]: s for s in snap["streams"]}
            self.assertTrue(by_name["camA"]["time_base"].endswith(
                str(tbA.denominator)))
            self.assertIsInstance(by_name["camA"]["pts"], int)
        finally:
            k.stop()

    def test_presentation_order_differs_from_packet_log_when_bframes(self):
        k = make_kernel([("camA", 0.0), ("camC", 0.0)])
        try:
            ptsA = [p[1] for p in k.decoders["camA"].packet_log]
            ptsC = [p[1] for p in k.decoders["camC"].packet_log]
            if self.has_av:
                # camA mp4 has B-frames: packet (decode) order is reordered
                self.assertTrue(any(ptsA[i] > ptsA[i + 1]
                                    for i in range(len(ptsA) - 1)),
                                f"expected reordered pts, got {ptsA[:12]}")
                self.assertFalse(any(ptsC[i] > ptsC[i + 1]
                                     for i in range(len(ptsC) - 1)))
            else:
                # stdlib packages keep presentation order in both logs
                self.assertEqual(ptsA, sorted(ptsA))
                self.assertEqual(ptsC, sorted(ptsC))
        finally:
            k.stop()

    def test_selection_by_pts_not_decode_completion(self):
        k = make_kernel([("camA", 0.0)])
        try:
            picks = k.step(0.5)["camA"]
            self.assertEqual(picks.state, OK)
            # 30fps: T=0.5 is exactly frame 15
            self.assertAlmostEqual(picks.frame.time, 0.5, places=6)
            self.assertEqual(picks.frame.frame_index, 15)
            self.assertAlmostEqual(picks.err, 0.0, places=6)
        finally:
            k.stop()


class TestCrossFpsPolicies(KernelTestBase):
    def test_nearest_vs_hold_and_error_report(self):
        k = make_kernel([("camA", 0.0), ("camC", 0.0)], policy="nearest")
        try:
            p = k.step(0.49)
            # camA 30fps: 0.49*30=14.7 -> nearest 15 (0.5000), hold 14 (0.4667)
            self.assertEqual(frame_num(p["camA"], 30), 15)
            self.assertAlmostEqual(p["camA"].err, 0.5 - 0.49, places=4)
            # camC 24fps: 0.49*24=11.76 -> nearest 12 (0.5000), hold 11 (0.4583)
            self.assertEqual(frame_num(p["camC"], 24), 12)
            self.assertAlmostEqual(p["camC"].err, 0.5 - 0.49, places=4)
        finally:
            k.stop()

        k = make_kernel([("camA", 0.0), ("camC", 0.0)], policy="hold")
        try:
            p = k.step(0.49)
            self.assertEqual(frame_num(p["camA"], 30), 14)
            self.assertAlmostEqual(p["camA"].err, 14 / 30 - 0.49, places=4)
            self.assertEqual(frame_num(p["camC"], 24), 11)
            self.assertAlmostEqual(p["camC"].err, 11 / 24 - 0.49, places=4)
            # error is reported, not hidden
            snap = k.snapshot()
            for s in snap["streams"]:
                self.assertGreater(s["metrics"]["max_err_ms"], 0.0)
        finally:
            k.stop()


class TestTimelineEdges(KernelTestBase):
    def test_early_end_others_continue(self):
        k = make_kernel([("camA", 0.0), ("camB", 0.0), ("camC", 0.0),
                         ("camD", 0.0)], policy="nearest")
        try:
            p = k.step(4.5)  # camB (4.0s) is over; the rest are not
            self.assertEqual(p["camB"].state, ENDED)
            self.assertEqual(p["camB"].frame.frame_index, 99)  # last kept
            for n in ("camA", "camC", "camD"):
                self.assertEqual(p[n].state, OK, n)
            # ended stream stays in the metrics — not dropped
            snap = k.snapshot()
            names = [s["name"] for s in snap["streams"]]
            self.assertEqual(sorted(names), ["camA", "camB", "camC", "camD"])
            mb = next(s for s in snap["streams"] if s["name"] == "camB")
            self.assertGreater(mb["metrics"]["ended_ticks"], 0)
            # and the composite still renders 4 cells
            cells = [build_cell_view(k, k.streams[n], p[n]) for n in k.streams]
            img = Composer(4).render(cells)
            self.assertEqual((img.w, img.h), (960, 840))
        finally:
            k.stop()

    def test_negative_offset(self):
        k = make_kernel([("camC", -0.8)], policy="nearest")
        try:
            p = k.step(0.5)["camC"]   # local target = 0.5 - (-0.8) = 1.3
            self.assertEqual(p.state, OK)
            self.assertAlmostEqual(p.target, 1.3, places=6)
            self.assertEqual(frame_num(p, 24), 31)  # 1.3*24 = 31.2
            self.assertAlmostEqual(p.frame.time, 31 / 24, places=4)
        finally:
            k.stop()

    def test_positive_offset_not_started(self):
        k = make_kernel([("camD", 1.2)], policy="nearest")
        try:
            p = k.step(0.5)["camD"]   # local target = -0.7
            self.assertEqual(p.state, NOT_STARTED)
            self.assertIsNone(p.frame)
        finally:
            k.stop()

    def test_ended_stream_stays_ended_after_prune(self):
        k = make_kernel([("camB", 0.0)], policy="nearest")
        try:
            p = k.step(5.0)["camB"]
            self.assertEqual(p.state, ENDED)
            for t in (6.0, 20.0, 100.0):   # prune must not kill the end state
                k.prune(t)
                p = k.step(t)["camB"]
                self.assertEqual(p.state, ENDED)
                self.assertIsNotNone(p.frame)
                self.assertEqual(p.frame.frame_index, 99)
        finally:
            k.stop()


# ------------------------------------------------------------- fake decoder
class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeDecoder:
    """Scriptable decoder: wait_for consumes the whole budget (a slow
    decoder) unless the test has already fed satisfying frames."""

    def __init__(self, name, path, clock=None, **kw):
        self.name, self.path, self.clock = name, path, clock
        self.frames = []
        self.eof = False
        self.fps = 30.0
        self.time_base = Fraction(1, 30)
        self.has_audio = False
        self.packet_log = []
        self.frames_decoded = 0
        self.decode_delay = 0.0

    def start(self):
        pass

    def stop(self):
        pass

    def feed(self, times, eof=False):
        for i, t in enumerate(times):
            self.frames.append(SimpleNamespace(
                time=t, pts=int(t * 30), time_base=Fraction(1, 30),
                arr_seq=len(self.frames), dec_seq=len(self.frames),
                pict="I", image=None, frame_index=len(self.frames),
                event_id=None, gap=False))
        self.frames.sort(key=lambda f: f.time)
        self.eof = self.eof or eof

    def snapshot(self):
        return list(self.frames), self.eof, None

    def wait_for(self, pred, timeout):
        if not pred(self.frames, self.eof, None):
            self.clock.advance(timeout)  # slow decode eats the budget
        return pred(self.frames, self.eof, None)

    def release_before(self, t):
        pass

    def nominal_span(self):
        return 1.0 / 30.0


class FakeClock2(FakeClock):
    def advance(self, dt):
        self.t += dt


def fake_kernel(continue_others, on_stall="hold", budget=0.1):
    clock = FakeClock2()
    fakes = {}
    cfgs = [StreamConfig(name="fast", path="x", offset=0.0),
            StreamConfig(name="slow", path="y", offset=0.0)]

    def factory(name, path, **kw):
        fakes[name] = FakeDecoder(name, path, clock=clock)
        return fakes[name]

    k = Kernel(cfgs, wait_budget=budget, on_stall=on_stall,
               continue_others_on_stall=continue_others,
               decoder_factory=factory, time_fn=clock)
    return k, fakes, clock


class TestBoundedWait(unittest.TestCase):
    def test_stall_and_continue_others(self):
        k, fakes, clock = fake_kernel(continue_others=True)
        fakes["fast"].feed([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
        p = k.step(0.25)
        self.assertEqual(p["fast"].state, OK)
        self.assertEqual(p["slow"].state, STALL)
        self.assertGreaterEqual(clock.t, 0.1)  # bounded wait consumed, not more
        snap = k.snapshot()
        mslow = next(s for s in snap["streams"] if s["name"] == "slow")
        self.assertEqual(mslow["metrics"]["stalls"], 1)  # reported, not dropped
        # slow stream recovers once frames arrive
        fakes["slow"].feed([0.2, 0.26])
        p = k.step(0.25)
        self.assertEqual(p["slow"].state, OK)
        self.assertAlmostEqual(p["slow"].frame.time, 0.26, places=6)  # nearest

    def test_stall_hold_all_when_configured(self):
        k, fakes, clock = fake_kernel(continue_others=False)
        fakes["fast"].feed([0.0, 0.1, 0.2])
        fakes["slow"].feed([0.0, 0.1, 0.2])
        p = k.step(0.1)
        self.assertEqual(p["fast"].state, OK)
        self.assertEqual(p["slow"].state, OK)
        first_frame = p["fast"].frame
        fakes["fast"].feed([0.3, 0.35, 0.4])
        p = k.step(0.35)  # slow stalls -> fast must hold its previous frame
        self.assertEqual(p["slow"].state, STALL)
        self.assertEqual(p["fast"].state, HELD)
        self.assertIs(p["fast"].frame, first_frame)

    def test_on_stall_blank(self):
        k, fakes, clock = fake_kernel(continue_others=True, on_stall="blank")
        fakes["fast"].feed([0.0, 0.1])
        p = k.step(0.1)
        self.assertEqual(p["slow"].state, STALL)
        self.assertIsNone(p["slow"].frame)


class TestMissingSegments(unittest.TestCase):
    """The synced demo pack: camB has a gap covering E3, camC is
    non-uniform, camD starts late. The kernel must surface GAP explicitly."""

    @classmethod
    def setUpClass(cls):
        from multicam.package import load_project
        cls.pack = os.path.join(ROOT, "demo_pack")
        if not os.path.isfile(os.path.join(cls.pack, "project.json")):
            from tools.make_synced_media import build_pack
            build_pack(cls.pack)
        cls.cfg = load_project(cls.pack)

    def _kernel(self, policy="nearest"):
        streams = [StreamConfig(
            name=s["name"],
            path=os.path.join(self.pack, s["path"]),
            offset=s["offset"]) for s in self.cfg["streams"]]
        k = Kernel(streams, policy=policy, wait_budget=5.0,
                   decoder_kwargs=dict(realtime=False))
        k.start()
        for d in k.decoders.values():
            d.preload()
        return k

    def test_gap_state_inside_camb_missing_segment(self):
        k = self._kernel()
        try:
            p = k.step(5.9)                      # inside camB 5.0-6.8 gap
            self.assertEqual(p["camB"].state, GAP)
            self.assertIsNotNone(p["camB"].frame)   # last pre-gap frame held
            self.assertGreater(abs(p["camB"].err), 0.5)
            # other cameras keep serving real frames
            for n in ("camA", "camC", "camD"):
                self.assertEqual(p[n].state, OK, n)
            self.assertGreater(k.snapshot()["streams"][1]["metrics"]["gaps"], 0)
        finally:
            k.stop()

    def test_non_uniform_camc_intervals(self):
        k = self._kernel()
        try:
            frames, _, _ = k.decoders["camC"].snapshot()
            times = [f.time for f in frames]
            diffs = [round(times[i + 1] - times[i], 4)
                     for i in range(len(times) - 1)]
            self.assertTrue(len(set(diffs)) > 1)  # genuinely non-uniform
        finally:
            k.stop()

    def test_late_start_camd(self):
        k = self._kernel()
        try:
            self.assertEqual(k.step(0.5)["camD"].state, NOT_STARTED)
            self.assertEqual(k.step(2.0)["camD"].state, OK)
        finally:
            k.stop()


class TestAppAndOutput(KernelTestBase):
    def config2(self, **over):
        cfg = {
            "streams": [
                {"name": "camA", "path": cam("camA"), "offset": 0.0},
                {"name": "camC", "path": cam("camC"), "offset": -0.8},
            ],
            "policy": "nearest",
            "reference": "virtual",
            "reference_options": ["virtual", "camA", "camC"],
            "audio_source": "camA",
            "wait_budget_ms": 150,
        }
        cfg.update(over)
        return cfg

    def test_audio_source_single_selectable(self):
        app = MultiCamApp(self.config2(), workdir=tempfile.mkdtemp())
        app.kernel.start()
        try:
            for d in app.kernel.decoders.values():
                self.assertTrue(d.ready.wait(10))
            app._collect_audio()
            self.assertEqual(sorted(app.audio_files), ["camA", "camC"])
            ok, _ = app.control({"action": "set_audio", "source": "camC"})
            self.assertTrue(ok)
            self.assertEqual(app.snapshot()["audio_source"], "camC")
            ok, _ = app.control({"action": "set_audio", "source": "mute"})
            self.assertTrue(ok)
            self.assertIsNone(app.snapshot()["audio_source"])
            ok, msg = app.control({"action": "set_audio", "source": "camZ"})
            self.assertFalse(ok)  # failure feeds back
            self.assertIn("unknown audio source", msg)
        finally:
            app.kernel.stop()

    def test_offline_render_and_frame_number_readback(self):
        tmp = tempfile.mkdtemp()
        app = MultiCamApp(self.config2(), workdir=tmp)
        info = app.render_offline(tmp, duration=1.0, fps=10)
        self.assertEqual(info["frames"], 10)
        pngs = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
        self.assertEqual(len(pngs), 10)
        with open(info["report"]) as fh:
            report = json.load(fh)
        # read the burned-in frame numbers back from the rendered composite
        from multicam.imglib import Canvas, load_rgb
        k = 5  # T = 0.5
        w, h, rgb = load_rgb(os.path.join(tmp, report["frames"][k]["png"]))
        img = Canvas(w, h)
        img.buf = bytearray(rgb)
        exp = report["frames"][k]["streams"]
        nA = read_frame_number(img, 0, 2)
        nC = read_frame_number(img, 1, 2)
        self.assertEqual(nA, int(round(exp["camA"]["pts_time"] * 30)))
        self.assertEqual(nC, int(round(exp["camC"]["pts_time"] * 24)))
        self.assertEqual(nA, 15)   # 0.5s * 30fps
        self.assertEqual(nC, 31)   # (0.5+0.8)s * 24fps = 31.2 -> 31
        self.assertEqual(sorted(report["metrics"]), ["camA", "camC"])
        self.assertTrue(os.path.exists(info["gif"]))

    def test_reference_clock_and_controls(self):
        app = MultiCamApp(self.config2(), workdir=tempfile.mkdtemp())
        ok, _ = app.control({"action": "set_reference", "reference": "camA"})
        self.assertTrue(ok)
        self.assertEqual(app.reference, "camA")
        ok, msg = app.control({"action": "set_reference", "reference": "camZ"})
        self.assertFalse(ok)
        ok, _ = app.control({"action": "set_policy", "policy": "hold"})
        self.assertTrue(ok)
        self.assertEqual(app.kernel.policy, "hold")
        ok, msg = app.control({"action": "bogus"})
        self.assertFalse(ok)
        app.kernel.stop()


class TestStrictLoader(unittest.TestCase):
    def test_missing_field_is_not_hidden_by_defaults(self):
        from multicam.package import load_project
        bad = tempfile.mkdtemp()
        os.makedirs(os.path.join(bad, "cameras", "x"))
        with open(os.path.join(bad, "project.json"), "w") as fh:
            json.dump({"streams": [{"name": "x"}]}, fh)  # path/offset missing
        with self.assertRaises(ValueError):
            load_project(bad)
        good = os.path.join(ROOT, "demo_pack")
        cfg = load_project(good)
        self.assertIn("virtual", cfg["reference_options"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
