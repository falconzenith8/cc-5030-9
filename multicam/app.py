"""MultiCamApp: wires the sync kernel, the composer and the panel.

Live mode runs a tick loop (~30 Hz): the reference clock produces T,
the kernel picks frames, the composer renders one composite image.
The reference clock can be the virtual wall clock or any stream's
presentation position.  Audio monitoring is a single selectable source
(extracted per stream, served to the panel) so sources never mix.
"""
import json
import os
import subprocess
import threading
import time

import numpy as np

from .compose import Composer, CellView
from .kernel import Kernel, StreamConfig, OK
from .media import StreamDecoder

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG = "ffmpeg"

TICK = 1.0 / 30.0


class MultiCamApp:
    def __init__(self, config, workdir="out"):
        self.config = config
        self.workdir = workdir
        os.makedirs(workdir, exist_ok=True)
        self.audio_dir = os.path.join(workdir, "audio_cache")
        os.makedirs(self.audio_dir, exist_ok=True)

        streams = [StreamConfig(**s) for s in config["streams"]]
        self.speed = float(config.get("speed", 1.0))
        self.kernel = Kernel(
            streams,
            policy=config.get("policy", "nearest"),
            wait_budget=config.get("wait_budget_ms", 150) / 1000.0,
            on_stall=config.get("on_stall", "hold"),
            continue_others_on_stall=config.get("continue_others_on_stall", True),
            decoder_kwargs=dict(realtime=True, speed_getter=lambda: self.speed),
        )
        for name, delay in config.get("simulate_decode_delay", {}).items():
            if name in self.kernel.streams:
                self.kernel.streams[name].decode_delay = delay
                self.kernel.decoders[name].decode_delay = delay

        self.reference = config.get("reference", "virtual")   # or a stream name
        self.audio_source = config.get("audio_source")        # None => mute
        self.T = 0.0
        self.playing = False
        self.composer = Composer(len(streams))
        self._png = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._t0 = None
        self._seek_base = 0.0
        self._dirty = True
        self.audio_files = {}

    # ------------------------------------------------------------- lifecycle
    def start(self):
        self.kernel.start()
        for name, dec in self.kernel.decoders.items():
            if not dec.ready.wait(timeout=15):
                self.kernel._log("error", f"{name}: decoder open timed out")
        self._extract_audio()
        self._t0 = time.monotonic()
        self._thread = threading.Thread(target=self._loop, name="multicam-loop",
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.kernel.stop()

    # ------------------------------------------------------------------ loop
    def _loop(self):
        while not self._stop.is_set():
            tick_start = time.monotonic()
            with self._lock:
                if self.playing:
                    self.T = self._clock_value()
                if self.playing or self._dirty:
                    picks = self.kernel.step(self.T)
                    self.kernel.prune(self.T)
                    cells = [self._cell_view(self.kernel.streams[n], picks[n])
                             for n in self.kernel.streams]
                    self._png = self.composer.render_png(cells)
                    self._dirty = False
            dt = time.monotonic() - tick_start
            if dt < TICK:
                time.sleep(TICK - dt)

    def _clock_value(self):
        if self.reference == "virtual":
            return self._seek_base + (time.monotonic() - self._t0) * self.speed
        # reference is a stream: production time follows its live
        # presentation position (newest decoded frame).  If that stream
        # stalls or ends, the whole timeline waits — it is the master.
        dec = self.kernel.decoders[self.reference]
        buf, _, _ = dec.snapshot()
        if buf:
            return buf[-1].time + self.kernel.streams[self.reference].offset
        return self.T

    def _cell_view(self, cfg, pick):
        return build_cell_view(self.kernel, cfg, pick)

    # ----------------------------------------------------------------- audio
    def _extract_audio(self):
        for name, dec in self.kernel.decoders.items():
            if not dec.has_audio:
                continue
            out = os.path.join(self.audio_dir, f"{name}.mp3")
            if not os.path.exists(out):
                src = self.kernel.streams[name].path
                subprocess.run(
                    [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                     "-i", src, "-vn", "-ac", "1", "-ar", "44100",
                     "-b:a", "96k", out], check=True)
            self.audio_files[name] = out

    # --------------------------------------------------------------- control
    def control(self, payload):
        """Panel control entry.  Returns (ok, message)."""
        with self._lock:
            action = payload.get("action")
            k = self.kernel
            if action == "play":
                if not self.playing:
                    self._t0 = time.monotonic()
                    self._seek_base = self.T
                    self.playing = True
            elif action == "pause":
                self.playing = False
            elif action == "seek":
                self.T = max(0.0, float(payload["t"]))
                self._seek_base = self.T
                self._t0 = time.monotonic()
                k.restart(start_at=max(0.0, self.T - 1.0), prod_t0=self.T)
            elif action == "set_policy":
                pol = payload["policy"]
                if pol not in ("nearest", "hold"):
                    return False, f"unknown policy {pol}"
                k.policy = pol
                k._log("info", f"policy -> {pol}")
            elif action == "set_reference":
                ref = payload["reference"]
                if ref != "virtual" and ref not in k.streams:
                    return False, f"unknown reference {ref}"
                self.reference = ref
                self._t0 = time.monotonic()
                self._seek_base = self.T
                k._log("info", f"reference clock -> {ref}")
            elif action == "set_audio":
                src = payload["source"]
                if src not in (None, "mute") and src not in k.streams:
                    return False, f"unknown audio source {src}"
                if src not in (None, "mute") and src not in self.audio_files:
                    return False, f"stream {src} has no audio track"
                self.audio_source = None if src in (None, "mute") else src
                k._log("info", f"audio monitor -> {self.audio_source or 'mute'}")
            elif action == "set_wait_ms":
                k.wait_budget = max(0.0, float(payload["ms"]) / 1000.0)
            elif action == "set_speed":
                self.speed = min(4.0, max(0.1, float(payload["speed"])))
                self._t0 = time.monotonic()
                self._seek_base = self.T
            elif action == "set_on_stall":
                v = payload["mode"]
                if v not in ("hold", "blank"):
                    return False, f"unknown on_stall {v}"
                k.on_stall = v
            elif action == "set_continue_others":
                k.continue_others_on_stall = bool(payload["value"])
            elif action == "set_decode_delay":
                name = payload["stream"]
                if name not in k.streams:
                    return False, f"unknown stream {name}"
                delay = max(0.0, float(payload["ms"]) / 1000.0)
                k.streams[name].decode_delay = delay
                k.decoders[name].decode_delay = delay
                k._log("info", f"{name} decode delay -> {delay * 1000:.0f}ms")
            else:
                return False, f"unknown action {action}"
            self._dirty = True
            return True, "ok"

    # --------------------------------------------------------------- outputs
    def latest_png(self):
        with self._lock:
            return self._png

    def snapshot(self):
        with self._lock:
            snap = self.kernel.snapshot()
            snap.update({
                "T": self.T,
                "playing": self.playing,
                "speed": self.speed,
                "reference": self.reference,
                "audio_source": self.audio_source,
                "audio_available": sorted(self.audio_files),
                "composite": {"width": self.composer.width,
                              "height": self.composer.height},
            })
            return snap

    # --------------------------------------------------------- offline render
    def render_offline(self, out_path, duration, fps=30):
        """Deterministic composite render: decode everything first, then
        step T at fixed intervals.  Writes the composite mp4 plus a JSON
        sidecar listing, per output frame, every stream's picked pts so
        frame numbers can be audited against the burned-in counters."""
        streams = [StreamConfig(**s) for s in self.config["streams"]]
        kernel = Kernel(
            streams,
            policy=self.kernel.policy,
            wait_budget=5.0,
            on_stall=self.kernel.on_stall,
            continue_others_on_stall=self.kernel.continue_others_on_stall,
            decoder_kwargs=dict(realtime=False),
        )
        kernel.start()
        for dec in kernel.decoders.values():
            dec.preload()
        composer = Composer(len(streams))
        names = list(kernel.streams)
        n_frames = int(round(duration * fps))
        report = {"fps": fps, "duration": duration, "policy": kernel.policy,
                  "offsets": {n: kernel.streams[n].offset for n in names},
                  "frames": []}
        proc = subprocess.Popen(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{composer.width}x{composer.height}", "-r", str(fps),
             "-i", "pipe:0", "-c:v", "libx264", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", out_path],
            stdin=subprocess.PIPE)
        try:
            for k in range(n_frames):
                T = k / fps
                picks = kernel.step(T)
                cells = [build_cell_view(kernel, kernel.streams[n], picks[n])
                         for n in names]
                img = composer.render(cells)
                proc.stdin.write(np.asarray(img).tobytes())
                report["frames"].append({
                    "k": k, "T": round(T, 6),
                    "streams": {n: {
                        "state": picks[n].state,
                        "pts": picks[n].frame.pts if picks[n].frame else None,
                        "pts_time": (round(picks[n].frame.time, 6)
                                     if picks[n].frame else None),
                        "arr_seq": (picks[n].frame.arr_seq
                                    if picks[n].frame else None),
                        "err_ms": (round(picks[n].err * 1000, 3)
                                   if picks[n].frame else None),
                    } for n in names},
                })
        finally:
            proc.stdin.close()
            rc = proc.wait()
            kernel.stop()
        if rc != 0:
            raise RuntimeError(f"ffmpeg composite encode failed rc={rc}")
        report["metrics"] = {s["name"]: s["metrics"] for s in kernel.snapshot()["streams"]}
        sidecar = os.path.splitext(out_path)[0] + ".report.json"
        with open(sidecar, "w") as fh:
            json.dump(report, fh, indent=1)
        return {"out": out_path, "report": sidecar, "frames": n_frames,
                "metrics": report["metrics"]}

    @staticmethod
    def _cell_view_for(kernel, name, pick):
        return build_cell_view(kernel, kernel.streams[name], pick)


def build_cell_view(kernel, cfg, pick):
    f = pick.frame
    dec = kernel.decoders[cfg.name]
    if f is not None:
        tb = f.time_base
        line1 = (f"pts {f.time:.4f}s (tb {tb.numerator}/{tb.denominator}"
                 f" #{f.pts})")
        line2 = (f"tgt {pick.target:.4f}s err {pick.err * 1000:+.1f}ms "
                 f"dec#{f.dec_seq} {f.pict} fps{(dec.fps or 0):g} "
                 f"off{cfg.offset:+.2f}")
        image = f.image
    else:
        line1 = f"tgt {pick.target:.4f}s  no frame"
        line2 = f"fps{(dec.fps or 0):g} off{cfg.offset:+.2f} state={pick.state}"
        image = None
    return CellView(cfg.name, pick.state, image, line1, line2)


def load_config(path):
    with open(path) as fh:
        return json.load(fh)
