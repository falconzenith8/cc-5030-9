"""On-disk source-material package + pure-stdlib frame decoder.

Package layout (self-contained, no container/codec dependency)::

    <pack>/
      project.json          # engineering config, strict-loaded by app
      sources.json          # provenance: generator, seed, parameters
      truth/
        events.json         # shared events on the master timeline
        ground_truth.json   # per-camera expected picks at audit times
      cameras/<cam>/
        camera.json         # fps, offset, frame records incl. gaps
        frames/f_00000.png  # one PNG per *recorded* frame
        audio.wav           # optional distinct sine tone

A camera's ``frames`` list records every frame that exists.  Two adjacent
records whose frame indices are not consecutive describe a missing
segment; the decoder simply never has a frame for those presentation
times, so the kernel reports NOT_STARTED/ENDED/STALL on real evidence
rather than on a fabricated black frame.
"""
import json
import os
import threading
import time
import wave
from collections import deque
from fractions import Fraction

from .imglib import load_rgb

PICT_I, PICT_P = "I", "P"


class FrameItem:
    """One decoded frame. Mirrors the legacy PyAV FrameItem surface so the
    kernel, composer and tests do not care which backend produced it."""

    __slots__ = ("arr_seq", "dec_seq", "pts", "time_base", "time", "pict",
                 "key_frame", "image", "frame_index", "event_id", "gap")

    def __init__(self, arr_seq, dec_seq, pts, time_base, pict, key_frame,
                 image, frame_index, event_id=None, gap=False):
        self.arr_seq = arr_seq
        self.dec_seq = dec_seq
        self.pts = pts
        self.time_base = time_base
        self.time = float(pts * time_base) if pts is not None else 0.0
        self.pict = pict
        self.key_frame = key_frame
        self.image = image                      # HxWx3 rgb bytearray
        self.frame_index = frame_index          # source frame counter
        self.event_id = event_id                # shared event burned in, if any
        self.gap = gap


class CameraPackage:
    """Random-access view over one camera directory of a material pack."""

    def __init__(self, camera_dir):
        with open(os.path.join(camera_dir, "camera.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
        self.name = meta["name"]
        self.dir = camera_dir
        self.fps = float(meta["fps"])
        self.offset = float(meta["offset"])
        self.width = int(meta["width"])
        self.height = int(meta["height"])
        self.time_base = Fraction(*meta["time_base"])
        self.frames = meta["frames"]            # list of records (dicts)
        self.gaps = meta.get("gaps", [])
        self.audio = os.path.join(camera_dir, "audio.wav")
        if not os.path.exists(self.audio):
            self.audio = None
        for rec in self.frames:
            rec["time"] = float(rec["time"])
        self._times = [r["time"] for r in self.frames]
        # shared across decoder instances (e.g. post-seek restarts):
        # source PNGs are immutable, decoded frames are cached once
        self.frame_cache = {}
        self.has_audio = self.audio is not None

    def frame_path(self, rec):
        return os.path.join(self.dir, "frames", rec["file"])

    def load_frame(self, rec, arr_seq):
        # cache only the decoded pixels; every load builds a fresh
        # FrameItem so decoder-specific state never leaks across restarts
        rgb = self.frame_cache.get(rec["file"])
        if rgb is None:
            _, _, rgb = load_rgb(self.frame_path(rec))
            self.frame_cache[rec["file"]] = rgb
        return FrameItem(
            arr_seq=arr_seq, dec_seq=arr_seq,
            pts=int(rec["pts"]), time_base=self.time_base,
            pict=rec.get("pict", PICT_P),
            key_frame=bool(rec.get("key_frame", False)),
            image=rgb, frame_index=int(rec["frame_index"]),
            event_id=rec.get("event_id"),
            gap=bool(rec.get("gap_after", False)))


class PackageDecoder(threading.Thread):
    """Decode a camera package on its own thread with the same surface as
    the legacy StreamDecoder (snapshot / wait_for / preload / release_before).

    ``realtime`` paces frame availability to the production clock via the
    frame's recorded presentation time — identical semantics to the live
    mp4 path — which keeps bounded-wait/stall behaviour testable.
    """

    _packages = {}
    _pkg_lock = threading.Lock()

    @classmethod
    def open_package(cls, path):
        """Reuse one CameraPackage (and its frame cache) per directory."""
        key = os.path.abspath(path)
        with cls._pkg_lock:
            pkg = cls._packages.get(key)
            if pkg is None:
                pkg = CameraPackage(path)
                cls._packages[key] = pkg
            return pkg

    def __init__(self, name, path, realtime=False, speed_getter=lambda: 1.0,
                 decode_delay=0.0, start_at=0.0, avail_offset=0.0, prod_t0=0.0,
                 package=None, bulk=False):
        super().__init__(name=f"dec-{name}", daemon=True)
        self.name = name
        self.path = path
        self.package = package or self.open_package(path)
        self.realtime = realtime
        self._speed_getter = speed_getter
        self.decode_delay = decode_delay
        self.start_at = start_at
        self.avail_offset = avail_offset
        self.prod_t0 = prod_t0

        self.time_base = self.package.time_base
        self.fps = self.package.fps
        self.has_audio = self.package.has_audio
        # package frames arrive in presentation order; keep a small
        # synthetic packet log so the snapshot surface stays identical
        self.packet_log = [(r["pts"], r["pts"]) for r in self.package.frames[:96]]
        self.frames_decoded = 0

        self._buf = deque()
        self._cond = threading.Condition()
        self._eof = False
        self._error = None
        self._stop_requested = False
        self.ready = threading.Event()
        self._preloaded = False
        self._bulk = bulk             # preload(): no pacing, no frame skip

    # ---------------------------------------------------------- thread body
    def run(self):
        try:
            self.ready.set()
            t0 = time.monotonic()
            for arr, rec in enumerate(self.package.frames):
                if self._stop_requested:
                    break
                item = self.package.load_frame(rec, arr)
                # a preloaded/bulk pass keeps every frame and never paces;
                # a live pass skips pre-start frames and follows the clock
                if not self._bulk and self.realtime and item.time < self.start_at:
                    continue
                if not self._bulk and self.realtime:
                    speed = max(self._speed_getter(), 1e-6)
                    due = t0 + (item.time + self.avail_offset
                                - self.prod_t0) / speed
                    delay = due - time.monotonic()
                    if delay > 0:
                        time.sleep(min(delay, 5.0))
                if self.decode_delay > 0:
                    time.sleep(self.decode_delay)
                with self._cond:
                    self._buf.append(item)
                    self.frames_decoded += 1
                    self._cond.notify_all()
        except Exception as exc:  # failure feeds back to the kernel
            with self._cond:
                self._error = exc
                self._eof = True
                self._cond.notify_all()
            return
        with self._cond:
            self._eof = True
            self._cond.notify_all()

    # ------------------------------------------------------------- queries
    def snapshot(self):
        with self._cond:
            return list(self._buf), self._eof, self._error

    def wait_for(self, pred, timeout):
        with self._cond:
            self._cond.wait_for(
                lambda: pred(self._buf, self._eof, self._error), timeout)
            return pred(self._buf, self._eof, self._error)

    def release_before(self, t):
        with self._cond:
            while len(self._buf) > 1 and self._buf[0].time < t:
                self._buf.popleft()

    def stop(self):
        self._stop_requested = True
        with self._cond:
            self._cond.notify_all()

    def preload(self, timeout=120.0):
        self._bulk = True
        if self.ident is None:
            self.start()
        self.join(timeout)
        if self.is_alive():
            raise TimeoutError(f"preload of {self.path} timed out")
        self._preloaded = True
        self._bulk = False

    def nominal_span(self):
        """Presentation span of the last frame — the real final frame
        interval, which differs from 1/fps for non-uniform timings."""
        recs = self.package.frames
        if len(recs) >= 2:
            return recs[-1]["time"] - recs[-2]["time"]
        return 1.0 / (self.fps or 30.0)


def load_project(pack_dir):
    """Strict project loader: missing/invalid required fields raise instead
    of being silently replaced by defaults (a wrong pack must not run on
    placeholder values)."""
    path = os.path.join(pack_dir, "project.json")
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    errors = []
    if not isinstance(cfg.get("streams"), list) or not cfg["streams"]:
        errors.append("streams: non-empty list required")
    seen = set()
    for i, s in enumerate(cfg.get("streams", [])):
        for key in ("name", "path", "offset"):
            if key not in s:
                errors.append(f"streams[{i}].{key} missing")
        if "name" in s:
            if s["name"] in seen:
                errors.append(f"duplicate stream name {s['name']}")
            seen.add(s["name"])
        cam_dir = os.path.join(pack_dir, s.get("path", ""))
        if not os.path.isfile(os.path.join(cam_dir, "camera.json")):
            errors.append(f"streams[{i}]: camera package missing at {s.get('path')}")
    if cfg.get("policy", "nearest") not in ("nearest", "hold"):
        errors.append("policy must be nearest|hold")
    ref = cfg.get("reference", "virtual")
    if ref != "virtual" and ref not in seen:
        errors.append(f"reference {ref!r} is not a known stream")
    if errors:
        raise ValueError("invalid project package: " + "; ".join(errors))
    return cfg


def load_sources(pack_dir):
    with open(os.path.join(pack_dir, "sources.json"), encoding="utf-8") as fh:
        return json.load(fh)


def load_events(pack_dir):
    with open(os.path.join(pack_dir, "truth", "events.json"), encoding="utf-8") as fh:
        return json.load(fh)


def open_wav(path):
    if not path or not os.path.exists(path):
        return None
    return wave.open(path, "rb")
