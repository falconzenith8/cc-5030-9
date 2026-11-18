"""Synchronisation kernel for the multi-camera preview.

One production timeline T (reference clock).  Each stream maps T into
its own local media time via its configured offset and picks a frame by
presentation timestamp — never by "which frame finished decoding k-th".

Policies:
  nearest — frame whose pts is closest to the target local time
  hold    — latest frame with pts <= target (floor / hold-last)

A stream whose needed frame has not surfaced within ``wait_budget``
becomes STALLED (bounded wait); whether the other streams keep
advancing is governed by ``continue_others_on_stall``.  Stalled/ended
streams stay in the metrics — nothing is dropped to make the numbers
look good.
"""
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from .media import StreamDecoder

OK = "OK"
STALL = "STALLED"
ENDED = "ENDED"
NOT_STARTED = "NOT_STARTED"
ERROR = "ERROR"
HELD = "HELD"
GAP = "GAP"          # camera has no frame covering this local time (missing segment)

EPS = 1e-6


@dataclass
class StreamConfig:
    name: str
    path: str
    offset: float = 0.0          # seconds; local_time = T - offset (may be negative)
    decode_delay: float = 0.0    # simulated slow decoder, seconds per frame
    # known production-time intervals with no frames for this camera;
    # a pick whose target lands inside one is reported GAP once the
    # distance to the nearest available frame exceeds gap_error_s.
    gaps: tuple = ()
    gap_error_s: object = None   # per-stream override of kernel threshold


@dataclass
class Pick:
    name: str
    state: str
    target: float                # local media time requested
    frame: object = None         # FrameItem or None
    err: float = 0.0             # signed picked.time - target (seconds)


class Kernel:
    def __init__(self, streams, policy="nearest", wait_budget=0.15,
                 on_stall="hold", continue_others_on_stall=True,
                 gap_error_s=None,
                 decoder_factory=StreamDecoder, time_fn=time.monotonic,
                 decoder_kwargs=None):
        assert policy in ("nearest", "hold")
        self.streams = {s.name: s for s in streams}
        self.policy = policy
        self.wait_budget = wait_budget
        self.on_stall = on_stall            # 'hold' shows last frame, 'blank' shows missing
        self.continue_others_on_stall = continue_others_on_stall
        # picks farther than this from any available frame while inside a
        # declared gap are surfaced as GAP; None keeps the legacy behaviour
        self.gap_error_s = gap_error_s
        self._time = time_fn
        self._decoder_kwargs = decoder_kwargs or {}
        self._factory = decoder_factory
        self.decoders = {}
        self._make_decoders(start_at=0.0)
        self.last = {}                      # name -> Pick
        self.metrics = {n: dict(picks=0, stalls=0, held=0, ended=0,
                                not_started=0, errors=0, gaps=0,
                                err_sum_ms=0.0, err_max_ms=0.0)
                        for n in self.streams}
        self.events = deque(maxlen=300)
        self._lock = threading.RLock()

    # ------------------------------------------------------------ lifecycle
    def _make_decoders(self, start_at, prod_t0=0.0):
        old = getattr(self, "decoders", {})
        for d in old.values():
            d.stop()
        self.decoders = {}
        for name, cfg in self.streams.items():
            kw = dict(self._decoder_kwargs)
            kw.setdefault("decode_delay", cfg.decode_delay)
            kw.setdefault("start_at", start_at)
            kw.setdefault("avail_offset", cfg.offset)
            kw.setdefault("prod_t0", prod_t0)
            self.decoders[name] = self._factory(cfg.name, cfg.path, **kw)

    def start(self):
        for d in self.decoders.values():
            d.start()

    def stop(self):
        for d in self.decoders.values():
            d.stop()

    def restart(self, start_at=0.0, prod_t0=0.0):
        with self._lock:
            self._make_decoders(start_at, prod_t0)
            for d in self.decoders.values():
                d.start()
            self.last = {}
            self._log("info", f"all streams restarted at {start_at:.2f}s")

    # --------------------------------------------------------------- events
    def _log(self, level, msg):
        self.events.append({"t": time.time(), "level": level, "msg": msg})

    # -------------------------------------------------------------- picking
    def step(self, T):
        """Advance every stream to production time T.  Returns {name: Pick}.

        The whole tick shares one bounded-wait budget so several stalled
        streams cannot each sleep a full budget while holding the loop
        lock: during a catch-up the tick returns quickly with STALLED
        picks and is retried on the next tick instead of blocking the
        composer for hundreds of milliseconds.
        """
        with self._lock:
            tick_deadline = self._time() + self.wait_budget
            picks = {}
            for name in self.streams:
                picks[name] = self._pick_one(name, T, tick_deadline)
            stalled = [n for n, p in picks.items() if p.state == STALL]
            if stalled and not self.continue_others_on_stall:
                for n, p in picks.items():
                    if p.state == OK:
                        prev = self.last.get(n)
                        picks[n] = Pick(n, HELD, p.target,
                                        prev.frame if prev else None,
                                        prev.err if prev else 0.0)
                        self.metrics[n]["held"] += 1
            for n, p in picks.items():
                if p.state in (OK, GAP):  # committed picks only (HELD reverts don't count)
                    m = self.metrics[n]
                    m["picks"] += 1
                    if p.state == GAP:
                        m["gaps"] += 1
                    err_ms = abs(p.err) * 1000.0
                    m["err_sum_ms"] += err_ms
                    m["err_max_ms"] = max(m["err_max_ms"], err_ms)
                self._transition(n, p, T)
            self.last = picks
            return picks

    def _pick_one(self, name, T, tick_deadline):
        cfg = self.streams[name]
        dec = self.decoders[name]
        target = T - cfg.offset
        if target < 0:
            # before this stream's first possible frame; no need to wait
            return Pick(name, NOT_STARTED, target)
        while True:
            buf, eof, err = dec.snapshot()
            if err is not None:
                self.metrics[name]["errors"] += 1
                return Pick(name, ERROR, target)
            le = [f for f in buf if f.time <= target + EPS]
            beyond = next((f for f in buf if f.time > target + EPS), None)
            if beyond is not None or eof:
                break
            remaining = min(tick_deadline - self._time(), self.wait_budget)
            if remaining <= 0:
                self.metrics[name]["stalls"] += 1
                prev = self.last.get(name)
                frame = prev.frame if (prev and self.on_stall == "hold") else None
                return Pick(name, STALL, target, frame,
                            prev.err if prev else 0.0)
            dec.wait_for(
                lambda b, e, x: x is not None or e or
                any(f.time > target + EPS for f in b),
                remaining)
        # selection is now decidable
        if not le:
            # No frame at or before target.  If a later frame is already
            # available this is the start of a missing segment: pick that
            # frame (nearest policy) rather than calling it NOT_STARTED, so
            # a gap keeps showing real picture instead of a blank cell.
            if beyond is not None:
                err = beyond.time - target
                state = OK
                if self._inside_gap(cfg, T) and self.gap_error_s is not None:
                    limit = (cfg.gap_error_s if cfg.gap_error_s is not None
                             else self.gap_error_s)
                    if abs(err) > limit:
                        state = GAP
                return Pick(name, state, target, beyond, err)
            return Pick(name, NOT_STARTED, target)
        last = le[-1]
        if eof:
            stream_last = buf[-1]  # buf is in presentation order
            dur = 1.0 / (dec.fps or 30.0)
            cover = dur if self.policy == "hold" else dur / 2.0
            if target > stream_last.time + cover:
                return Pick(name, ENDED, target, stream_last,
                            stream_last.time - target)
        if self.policy == "hold":
            chosen = last
        else:
            chosen = last if beyond is None else min(
                (last, beyond), key=lambda f: abs(f.time - target))
        err = chosen.time - target
        state = OK
        if self._inside_gap(cfg, T) and self.gap_error_s is not None:
            limit = (cfg.gap_error_s if cfg.gap_error_s is not None
                     else self.gap_error_s)
            if abs(err) > limit:
                state = GAP
        return Pick(name, state, target, chosen, err)

    @staticmethod
    def _inside_gap(cfg, production_T):
        # gaps are declared on the production timeline T
        return any(lo - EPS <= production_T <= hi + EPS
                   for lo, hi in cfg.gaps)

    def _transition(self, name, pick, T):
        m = self.metrics[name]
        if pick.state == ENDED:
            m["ended"] += 1
        elif pick.state == NOT_STARTED:
            m["not_started"] += 1
        prev = self.last.get(name)
        prev_state = prev.state if prev else None
        if pick.state != prev_state:
            lvl = "warn" if pick.state in (STALL, ERROR) else "info"
            self._log(lvl, f"{name}: {prev_state or '-'} -> {pick.state} "
                           f"@T={T:.3f}s target={pick.target:.3f}s")

    # ------------------------------------------------------------ housekeeping
    def prune(self, T):
        """Bound decoder memory: drop frames well behind the playhead."""
        for name, dec in self.decoders.items():
            dec.release_before(T - self.streams[name].offset - 2.0)

    # --------------------------------------------------------------- report
    def snapshot(self):
        with self._lock:
            out = {"policy": self.policy,
                   "wait_budget_ms": round(self.wait_budget * 1000, 1),
                   "on_stall": self.on_stall,
                   "continue_others_on_stall": self.continue_others_on_stall,
                   "streams": []}
            for name, cfg in self.streams.items():
                dec = self.decoders[name]
                m = self.metrics[name]
                p = self.last.get(name)
                f = p.frame if p else None
                tb = f.time_base if f else dec.time_base
                out["streams"].append({
                    "name": name,
                    "offset": cfg.offset,
                    "fps": dec.fps,
                    "time_base": f"{tb.numerator}/{tb.denominator}" if tb else None,
                    "state": p.state if p else "INIT",
                    "target": p.target if p else None,
                    "pts": f.pts if f else None,
                    "pts_time": f.time if f else None,
                    "err_ms": (p.err * 1000.0) if p and f else None,
                    "arr_seq": f.arr_seq if f else None,
                    "dec_seq": f.dec_seq if f else None,
                    "pict": f.pict if f else None,
                    "frames_decoded": dec.frames_decoded,
                    "decode_delay": dec.decode_delay,
                    "has_audio": dec.has_audio,
                    "gaps_declared": [list(g) for g in cfg.gaps],
                    "in_gap": self._inside_gap(cfg, p.target + cfg.offset) if p else False,
                    "packet_log_head": dec.packet_log[:16],
                    "metrics": {
                        "picks": m["picks"],
                        "stalls": m["stalls"],
                        "held": m["held"],
                        "ended_ticks": m["ended"],
                        "not_started_ticks": m["not_started"],
                        "errors": m["errors"],
                        "gaps": m["gaps"],
                        "mean_err_ms": (m["err_sum_ms"] / m["picks"]
                                        if m["picks"] else 0.0),
                        "max_err_ms": m["err_max_ms"],
                    },
                })
            out["events"] = list(self.events)[-60:]
            return out
