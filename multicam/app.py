"""MultiCamApp: wires the sync kernel, the composer and the panel.

Live mode runs a tick loop (~30 Hz): the reference clock produces T,
the kernel picks frames, the composer renders one composite image.
The reference clock can be the virtual wall clock or any stream's
presentation position.  Audio monitoring is a single selectable source
(the package's own WAV, or an extracted track for legacy mp4 sources) so
sources never mix.
"""
import json
import os
import shutil
import subprocess
import threading
import time

from .compose import Composer, CellView
from .imglib import write_png, write_gif
from .kernel import Kernel, StreamConfig
from .media import make_decoder, _HAS_AV

TICK = 1.0 / 30.0


class MultiCamApp:
    def __init__(self, config, workdir="out", pack_dir=None):
        self.config = config
        self.workdir = workdir
        self.pack_dir = pack_dir
        os.makedirs(workdir, exist_ok=True)
        self.audio_dir = os.path.join(workdir, "audio_cache")
        os.makedirs(self.audio_dir, exist_ok=True)

        streams = [self._resolve_stream(s) for s in config["streams"]]
        self.speed = float(config.get("speed", 1.0))
        self.kernel = Kernel(
            streams,
            policy=config.get("policy", "nearest"),
            wait_budget=config.get("wait_budget_ms", 150) / 1000.0,
            on_stall=config.get("on_stall", "hold"),
            continue_others_on_stall=config.get(
                "continue_others_on_stall", True),
            decoder_kwargs=dict(realtime=True, speed_getter=lambda: self.speed),
        )
        for name, delay in config.get("simulate_decode_delay", {}).items():
            if name in self.kernel.streams:
                self.kernel.streams[name].decode_delay = delay
                self.kernel.decoders[name].decode_delay = delay

        refs = config.get("reference_options", ["virtual"])
        self.reference_options = refs
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

    def _resolve_stream(self, s):
        cfg = dict(s)
        path = cfg["path"]
        if self.pack_dir and not os.path.isabs(path) and not os.path.exists(path):
            candidate = os.path.join(self.pack_dir, path)
            if os.path.exists(candidate):
                cfg["path"] = candidate
        return StreamConfig(**cfg)

    # ------------------------------------------------------------- lifecycle
    def start(self):
        self.kernel.start()
        for name, dec in self.kernel.decoders.items():
            if not dec.ready.wait(timeout=15):
                self.kernel._log("error", f"{name}: decoder open timed out")
        self._collect_audio()
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
                    self.T = self._clock_value(tick_start)
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

    def _clock_value(self, now=None):
        now = time.monotonic() if now is None else now
        if self.reference == "virtual":
            return self._seek_base + (now - self._t0) * self.speed
        # reference is a stream master. In a live pass the newest available
        # frame drives T; when frames are bulk-preloaded the whole buffer is
        # present at once, so pace the master by wall clock and clamp it to
        # recorded frames (a gap/stall then makes the timeline wait).
        dec = self.kernel.decoders[self.reference]
        buf, _, _ = dec.snapshot()
        if not buf:
            return self.T
        if getattr(dec, "_preloaded", False):
            target_local = (self._seek_base
                            + (now - self._t0) * self.speed
                            - self.kernel.streams[self.reference].offset)
            eligible = [f for f in buf if f.time <= target_local + 1e-9]
            frame = eligible[-1] if eligible else buf[0]
            return frame.time + self.kernel.streams[self.reference].offset
        return buf[-1].time + self.kernel.streams[self.reference].offset

    def _cell_view(self, cfg, pick):
        return build_cell_view(self.kernel, cfg, pick)

    # ----------------------------------------------------------------- audio
    def _collect_audio(self):
        """Package cameras already carry WAV; legacy mp4 streams need an
        ffmpeg extraction (only attempted when that backend is in use)."""
        for name, dec in self.kernel.decoders.items():
            wav = getattr(dec.package, "audio", None) if hasattr(dec, "package") else None
            if wav and os.path.exists(wav):
                dst = os.path.join(self.audio_dir, f"{name}.wav")
                if not os.path.exists(dst):
                    shutil.copyfile(wav, dst)
                self.audio_files[name] = dst
            elif getattr(dec, "has_audio", False):
                dst = os.path.join(self.audio_dir, f"{name}.mp3")
                if os.path.exists(dst):
                    self.audio_files[name] = dst
                elif shutil.which("ffmpeg"):
                    subprocess.run(
                        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                         "-i", self.kernel.streams[name].path, "-vn", "-ac", "1",
                         "-ar", "44100", "-b:a", "96k", dst], check=True)
                    self.audio_files[name] = dst

    # --------------------------------------------------------------- control
    def control(self, payload):
        """Panel control entry.  Returns (ok, message)."""
        with self._lock:
            action = payload.get("action")
            k = self.kernel
            if action == "play":
                if not self.playing:
                    # ensure every decoder has reached the playhead before
                    # starting the clock, otherwise the wall clock advances
                    # while a camera is still catching up (clock drift).
                    # Cached package frames make this a short bounded wait.
                    for name, dec in k.decoders.items():
                        target = self.T - k.streams[name].offset
                        if target < 0:
                            continue
                        deadline = time.monotonic() + k.wait_budget + 2.0
                        dec.wait_for(
                            lambda b, e, x, t=target:
                            x is not None or e or
                            any(f.time > t for f in b),
                            max(0.0, deadline - time.monotonic()))
                    self._t0 = time.monotonic()
                    self._seek_base = self.T
                    self.playing = True
            elif action == "pause":
                if self.playing:
                    # freeze the reached time as the new anchor, otherwise
                    # the wall-clock delta keeps accruing while paused and
                    # jumps on the next play
                    self.T = self._clock_value()
                    self._seek_base = self.T
                    self._t0 = time.monotonic()
                self.playing = False
            elif action == "seek":
                self.playing = False
                self.T = max(0.0, float(payload["t"]))
                self._seek_base = self.T
                self._t0 = time.monotonic()
                # restart live decoders at the new position.  Frames are
                # cached in the CameraPackage, so the re-decode is cheap and
                # realtime availability pacing is preserved (no bulk EOF).
                k.restart(start_at=max(0.0, self.T - 1.0),
                          prod_t0=self.T, preload=False)
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
                "reference_options": self.reference_options,
                "audio_source": self.audio_source,
                "audio_available": sorted(self.audio_files),
                "audio_format": {n: ("wav" if p.endswith(".wav") else "mp3")
                                 for n, p in self.audio_files.items()},
                "composite": {"width": self.composer.width,
                              "height": self.composer.height},
            })
            return snap

    # --------------------------------------------------------- offline render
    def render_offline(self, out_dir, duration, fps=10):
        """Deterministic composite render: decode everything first, then
        step T at fixed intervals.  Writes one PNG per output frame plus a
        JSON sidecar listing, per output frame, every stream's picked pts,
        state and event tag so the common-event correspondence is auditable.
        When ImageMagick is available an animated GIF summary is produced.
        """
        os.makedirs(out_dir, exist_ok=True)
        streams = [self._resolve_stream(s) for s in self.config["streams"]]
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
        png_paths = []
        gif_frames = []
        for k in range(n_frames):
            T = k / fps
            picks = kernel.step(T)
            cells = [build_cell_view(kernel, kernel.streams[n], picks[n])
                     for n in names]
            img = composer.render(cells)
            path = os.path.join(out_dir, f"comp_{k:04d}.png")
            write_png(path, composer.width, composer.height, img.buf)
            png_paths.append(path)
            gif_frames.append(img)
            report["frames"].append({
                "k": k, "T": round(T, 6),
                "png": os.path.basename(path),
                "streams": {n: {
                    "state": picks[n].state,
                    "pts": picks[n].frame.pts if picks[n].frame else None,
                    "pts_time": (round(picks[n].frame.time, 6)
                                 if picks[n].frame else None),
                    "frame_index": (picks[n].frame.frame_index
                                    if picks[n].frame else None),
                    "event_id": (picks[n].frame.event_id
                                 if picks[n].frame else None),
                    "arr_seq": (picks[n].frame.arr_seq
                                if picks[n].frame else None),
                    "err_ms": (round(picks[n].err * 1000, 3)
                               if picks[n].frame else None),
                } for n in names},
            })
        kernel.stop()
        report["metrics"] = {
            s["name"]: s["metrics"] for s in kernel.snapshot()["streams"]}
        sidecar = os.path.join(out_dir, "composite.report.json")
        with open(sidecar, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
        gif = os.path.join(out_dir, "composite.gif")
        write_gif(gif, gif_frames, [int(1000 / fps)] * len(gif_frames))
        return {"out_dir": out_dir, "report": sidecar, "frames": n_frames,
                "gif": gif, "metrics": report["metrics"]}


def build_cell_view(kernel, cfg, pick):
    f = pick.frame
    dec = kernel.decoders[cfg.name]
    if f is not None:
        tb = f.time_base
        line1 = (f"PTS {f.time:.4f}S TB {tb.numerator}/{tb.denominator}"
                 f" #{f.pts}")
        line2 = (f"TGT {pick.target:.4f}S ERR {pick.err * 1000:+.1f}MS "
                 f"DEC#{f.dec_seq} {f.pict} FPS{(dec.fps or 0):G} "
                 f"OFF{cfg.offset:+.2f}")
        if f.event_id:
            line2 += f" {f.event_id}"
        image = f.image
    else:
        line1 = f"TGT {pick.target:.4f}S NO FRAME"
        line2 = f"FPS{(dec.fps or 0):G} OFF{cfg.offset:+.2f} STATE={pick.state}"
        image = None
    return CellView(cfg.name, pick.state, image, line1, line2)


def load_config(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_pack(pack_dir):
    """Load a self-made material pack through the strict project loader."""
    from .package import load_project
    cfg = load_project(pack_dir)
    return MultiCamApp(cfg, workdir=os.path.join(pack_dir, "runtime"),
                       pack_dir=pack_dir)
