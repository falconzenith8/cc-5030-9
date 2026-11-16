"""Per-stream decoding.

Every stream is decoded on its own thread and keeps its own time base
(raw pts + time_base) and its own decode order (packet arrival order is
logged; frames are tagged with the decode-pass sequence number that
surfaced them).  Nothing here assumes streams share a clock: alignment
is the kernel's job and is done purely on presentation timestamps.
"""
import threading
import time
from collections import deque

import av

PICT_NAMES = {0: "?", 1: "I", 2: "P", 3: "B", 4: "S"}


class FrameItem:
    __slots__ = ("arr_seq", "dec_seq", "pts", "time_base", "time", "pict",
                 "key_frame", "image")

    def __init__(self, arr_seq, dec_seq, pts, time_base, pict, key_frame, image):
        self.arr_seq = arr_seq          # arrival order from decoder (presentation rank)
        self.dec_seq = dec_seq          # index of the packet whose decode() surfaced it
        self.pts = pts                  # raw pts in this stream's own time base
        self.time_base = time_base      # this stream's own time base (Fraction)
        self.time = float(pts * time_base) if pts is not None else 0.0
        self.pict = pict
        self.key_frame = key_frame
        self.image = image              # HxWx3 uint8 rgb24


class StreamDecoder(threading.Thread):
    """Decode one video file.  Frames become available in presentation
    order (the decoder reorders B-frames internally); the packet-level
    decode order is recorded in ``packet_log`` so the reordering is
    observable.  With ``realtime=True`` frame availability is paced to
    the presentation clock, which is what makes bounded-wait meaningful
    in the live panel."""

    def __init__(self, name, path, realtime=False, speed_getter=lambda: 1.0,
                 decode_delay=0.0, start_at=0.0, avail_offset=0.0, prod_t0=0.0):
        super().__init__(name=f"dec-{name}", daemon=True)
        self.name = name
        self.path = path
        self.realtime = realtime
        self._speed_getter = speed_getter
        self.decode_delay = decode_delay
        self.start_at = start_at
        # a frame with local pts p is "filmed" at production time p+offset;
        # it becomes available when the production clock reaches that time
        self.avail_offset = avail_offset
        self.prod_t0 = prod_t0        # production time when decoding (re)started

        self.time_base = None
        self.fps = None
        self.has_audio = False
        self.packet_log = []            # (dts, pts) per packet, decode order
        self.frames_decoded = 0

        self._buf = deque()
        self._cond = threading.Condition()
        self._eof = False
        self._error = None
        self._stop_requested = False
        self.ready = threading.Event()

    # ---------------------------------------------------------- thread body
    def run(self):
        try:
            self._run()
        except Exception as exc:  # failure feeds back to the kernel
            with self._cond:
                self._error = exc
                self._eof = True
                self._cond.notify_all()
            self.ready.set()

    def _run(self):
        container = av.open(self.path)
        try:
            vs = container.streams.video[0]
            self.time_base = vs.time_base
            self.fps = float(vs.average_rate or vs.base_rate)
            self.has_audio = len(container.streams.audio) > 0
            self.ready.set()
            t0 = time.monotonic()
            arr = 0
            for pkt_idx, pkt in enumerate(container.demux(vs)):
                if self._stop_requested:
                    break
                if pkt.dts is not None and len(self.packet_log) < 96:
                    self.packet_log.append((pkt.dts, pkt.pts))
                for frame in pkt.decode():
                    if self._stop_requested:
                        break
                    pts = frame.pts
                    item = FrameItem(
                        arr_seq=arr,
                        dec_seq=pkt_idx,
                        pts=pts,
                        time_base=frame.time_base,
                        pict=PICT_NAMES.get(int(frame.pict_type), "?"),
                        key_frame=bool(frame.key_frame),
                        image=frame.to_ndarray(format="rgb24"),
                    )
                    arr += 1
                    if item.time < self.start_at:
                        continue  # seek: decode but discard earlier frames
                    if self.realtime:
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
        finally:
            container.close()
            with self._cond:
                self._eof = True
                self._cond.notify_all()

    # ------------------------------------------------------------- queries
    def snapshot(self):
        """(frames, eof, error) — frames sorted by presentation time."""
        with self._cond:
            return list(self._buf), self._eof, self._error

    def wait_for(self, pred, timeout):
        """Block until pred(frames, eof, error) is true or timeout (seconds)."""
        with self._cond:
            self._cond.wait_for(
                lambda: pred(self._buf, self._eof, self._error), timeout)
            return pred(self._buf, self._eof, self._error)

    def release_before(self, t):
        """Drop buffered frames older than t (memory bound; kernel keeps
        the frames it currently displays).  Always keeps the newest
        frame: after EOF that last frame is what lets the kernel keep
        reporting ENDED instead of losing the stream."""
        with self._cond:
            while len(self._buf) > 1 and self._buf[0].time < t:
                self._buf.popleft()

    def stop(self):
        self._stop_requested = True
        with self._cond:
            self._cond.notify_all()

    # ------------------------------------------------------------ test hook
    def preload(self, timeout=120.0):
        """Decode everything (used by deterministic offline runs)."""
        if self.ident is None:
            self.start()
        self.join(timeout)
        if self.is_alive():
            raise TimeoutError(f"preload of {self.path} timed out")
