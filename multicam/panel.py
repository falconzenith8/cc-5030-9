"""Production panel for the multi-camera preview.

A stdlib HTTP server (multi-client via ThreadingHTTPServer) that serves
the control page, the live composite PNG, per-stream audio sources and
the kernel state.  Every control goes back into the kernel through
MultiCamApp.control, and kernel failures (decode errors, stalls, ended
streams) come back to the page through /api/state.
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

INDEX_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>多机位同步预监面板</title>
<style>
  body { background:#141419; color:#ddd; font:14px/1.4 system-ui,sans-serif;
         margin:0; padding:12px; }
  h1 { font-size:18px; margin:0 0 10px; }
  .bar { display:flex; gap:10px; flex-wrap:wrap; align-items:center;
         background:#1e1e26; padding:8px 10px; border-radius:8px; margin-bottom:10px; }
  .bar label { color:#9aa; }
  button, select, input { background:#2a2a35; color:#ddd; border:1px solid #444;
         border-radius:5px; padding:4px 8px; }
  button { cursor:pointer; }
  #stage { text-align:center; }
  #comp { max-width:100%; border:1px solid #333; border-radius:6px;
          background:#000; image-rendering:auto; }
  table { border-collapse:collapse; width:100%; margin-top:10px; font-size:12.5px; }
  th, td { border:1px solid #333; padding:3px 6px; text-align:right;
           font-family:ui-monospace,monospace; }
  th { background:#22222c; color:#9ab; }
  td.name, th.name { text-align:left; }
  .st-OK { color:#5fd07a; } .st-STALLED { color:#f0a03c; } .st-ENDED { color:#7c9be0; }
  .st-HELD { color:#e0d060; } .st-ERROR { color:#e05555; } .st-NOT_STARTED { color:#999; }
  #events { height:130px; overflow-y:auto; background:#101014; border:1px solid #2c2c36;
            border-radius:6px; padding:6px 8px; font:12px ui-monospace,monospace;
            margin-top:10px; white-space:pre-wrap; }
  .warn { color:#f0a03c; } .error { color:#e05555; }
  #clock { font:16px ui-monospace,monospace; color:#8fd; }
</style>
</head>
<body>
<h1>多机位同步预监面板 <span style="font-size:12px;color:#789">multicam sync preview</span></h1>
<div class="bar">
  <button id="playpause">播放</button>
  <span id="clock">T=0.000</span>
  <label>取帧策略 <select id="policy">
    <option value="nearest">nearest 最近帧</option>
    <option value="hold">hold 保持(≤target)</option></select></label>
  <label>参考时钟 <select id="reference"><option value="virtual">virtual 虚拟钟</option></select></label>
  <label>音频监听 <select id="audio"><option value="mute">静音</option></select></label>
  <label>有界等待 <input id="waitms" type="number" min="0" max="2000" step="10" style="width:70px"> ms</label>
  <label>速度 <select id="speed"><option>0.5</option><option selected>1.0</option>
    <option>2.0</option></select></label>
  <label>慢解码时其余机位 <select id="cont"><option value="1">继续</option>
    <option value="0">保持全场</option></select></label>
  <label>停滞显示 <select id="onstall"><option value="hold">保持末帧</option>
    <option value="blank">黑场</option></select></label>
  <label>模拟慢解码 <select id="delaystream"></select>
    <input id="delayms" type="number" min="0" max="2000" step="10" style="width:70px"> ms
    <button id="applydelay">应用</button></label>
</div>
<div id="stage"><img id="comp" alt="composite"></div>
<table id="streams">
  <thead><tr>
    <th class="name">机位</th><th>状态</th><th>偏移s</th><th>fps</th><th>时间基</th>
    <th>目标pts</th><th>选中pts</th><th>原始pts</th><th>误差ms</th>
    <th>到达序</th><th>解码包序</th><th>帧型</th><th>已解码</th>
    <th>取帧数</th><th>停滞</th><th>平均误差</th><th>最大误差</th>
  </tr></thead><tbody></tbody>
</table>
<div id="events"></div>
<audio id="mon" style="display:none"></audio>
<script>
const $ = id => document.getElementById(id);
let playing = false, streams = [], lastAudio = null;

async function ctl(payload) {
  const r = await fetch('/api/control', {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const j = await r.json();
  if (!j.ok) log('error', '控制失败: ' + j.error);
  refresh();
}
function log(level, msg) {
  const e = $('events');
  const d = document.createElement('div');
  d.className = level; d.textContent = msg;
  e.appendChild(d); e.scrollTop = e.scrollHeight;
  while (e.children.length > 200) e.removeChild(e.firstChild);
}
$('playpause').onclick = () => ctl({action: playing ? 'pause' : 'play'});
$('policy').onchange = e => ctl({action:'set_policy', policy:e.target.value});
$('reference').onchange = e => ctl({action:'set_reference', reference:e.target.value});
$('audio').onchange = e => ctl({action:'set_audio', source:e.target.value});
$('waitms').onchange = e => ctl({action:'set_wait_ms', ms:+e.target.value});
$('speed').onchange = e => ctl({action:'set_speed', speed:+e.target.value});
$('cont').onchange = e => ctl({action:'set_continue_others', value:e.target.value==='1'});
$('onstall').onchange = e => ctl({action:'set_on_stall', mode:e.target.value});
$('applydelay').onclick = () => ctl({action:'set_decode_delay',
  stream:$('delaystream').value, ms:+$('delayms').value});

function fillSelect(sel, items, keep) {
  const cur = keep ? sel.value : null;
  const first = sel.querySelector('option');
  sel.innerHTML = ''; if (first) sel.appendChild(first);
  for (const it of items) {
    const o = document.createElement('option');
    o.value = it; o.textContent = it; sel.appendChild(o);
  }
  if (cur && [...sel.options].some(o => o.value === cur)) sel.value = cur;
}

async function refresh() {
  let s;
  try { s = await (await fetch('/api/state')).json(); }
  catch (e) { return; }
  playing = s.playing;
  $('playpause').textContent = playing ? '暂停' : '播放';
  $('clock').textContent = 'T=' + s.T.toFixed(3) + 's' +
    (s.reference !== 'virtual' ? ' (跟随 ' + s.reference + ')' : '');
  streams = s.streams.map(x => x.name);
  fillSelect($('reference'), streams, true);
  fillSelect($('audio'), s.audio_available, true);
  fillSelect($('delaystream'), streams, true);
  if (document.activeElement !== $('policy')) $('policy').value = s.policy;
  if (document.activeElement !== $('reference')) $('reference').value = s.reference;
  if (document.activeElement !== $('audio')) $('audio').value = s.audio_source || 'mute';
  if (document.activeElement !== $('waitms')) $('waitms').value = s.wait_budget_ms;
  $('cont').value = s.continue_others_on_stall ? '1' : '0';
  $('onstall').value = s.on_stall;

  const tb = document.querySelector('#streams tbody');
  tb.innerHTML = '';
  for (const st of s.streams) {
    const m = st.metrics;
    const tr = document.createElement('tr');
    tr.innerHTML =
      `<td class="name">${st.name}</td><td class="st-${st.state}">${st.state}</td>` +
      `<td>${st.offset.toFixed(2)}</td><td>${st.fps ? st.fps.toFixed(2) : '-'}</td>` +
      `<td>${st.time_base || '-'}</td>` +
      `<td>${st.target == null ? '-' : st.target.toFixed(4)}</td>` +
      `<td>${st.pts_time == null ? '-' : st.pts_time.toFixed(4)}</td>` +
      `<td>${st.pts == null ? '-' : st.pts}</td>` +
      `<td>${st.err_ms == null ? '-' : st.err_ms.toFixed(1)}</td>` +
      `<td>${st.arr_seq == null ? '-' : st.arr_seq}</td>` +
      `<td>${st.dec_seq == null ? '-' : st.dec_seq}</td>` +
      `<td>${st.pict || '-'}</td><td>${st.frames_decoded}</td>` +
      `<td>${m.picks}</td><td>${m.stalls}</td>` +
      `<td>${m.mean_err_ms.toFixed(1)}</td><td>${m.max_err_ms.toFixed(1)}</td>`;
    tb.appendChild(tr);
  }
  for (const ev of s.events.slice(-8)) {
    const d = new Date(ev.t * 1000).toLocaleTimeString();
    log(ev.level, `[${d}] ${ev.msg}`);
  }
  // audio monitoring: exactly one <audio> element follows the chosen source
  const a = $('mon');
  const want = s.audio_source;
  if (want !== lastAudio) {
    lastAudio = want;
    a.pause(); a.removeAttribute('src');
    if (want) { a.src = '/audio/' + want + '.mp3'; a.load(); }
  }
  if (want) {
    const off = (s.streams.find(x => x.name === want) || {offset:0}).offset;
    const at = s.T - off;
    a.playbackRate = s.speed;
    if (s.playing && a.paused) a.play().catch(() => {});
    if (!s.playing && !a.paused) a.pause();
    if (s.playing && Math.abs(a.currentTime - at) > 0.3) a.currentTime = Math.max(0, at);
  }
}
// composite refresh
setInterval(() => { $('comp').src = '/frame.png?ts=' + Date.now(); }, 150);
setInterval(refresh, 400);
refresh();
</script>
</body>
</html>
"""


class PanelServer:
    def __init__(self, app, host="127.0.0.1", port=8765):
        self.app = app
        self.host, self.port = host, port
        handler = self._make_handler()
        self.httpd = ThreadingHTTPServer((host, port), handler)

    def _make_handler(self):
        app = self.app

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path == "/":
                    self._send(200, INDEX_HTML.encode(), "text/html; charset=utf-8")
                elif path == "/api/state":
                    self._send(200, json.dumps(app.snapshot()).encode())
                elif path == "/frame.png":
                    png = app.latest_png()
                    if png is None:
                        self._send(503, b"{}")
                    else:
                        self._send(200, png, "image/png")
                elif path.startswith("/audio/"):
                    name = os.path.basename(path)[:-4] if path.endswith(".mp3") else ""
                    f = app.audio_files.get(name)
                    if f and os.path.exists(f):
                        with open(f, "rb") as fh:
                            self._send(200, fh.read(), "audio/mpeg")
                    else:
                        self._send(404, b"{}")
                else:
                    self._send(404, b"{}")

            def do_POST(self):
                if self.path.split("?", 1)[0] != "/api/control":
                    self._send(404, b"{}")
                    return
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    payload = json.loads(self.rfile.read(n) or b"{}")
                    ok, msg = app.control(payload)
                except Exception as exc:  # control failure feeds back to panel
                    ok, msg = False, str(exc)
                code = 200 if ok else 400
                self._send(code, json.dumps({"ok": ok, "error": None if ok else msg}).encode())

        return Handler

    def serve_forever(self):
        self.httpd.serve_forever()

    def start_background(self):
        t = threading.Thread(target=self.serve_forever, name="panel", daemon=True)
        t.start()
        return t

    def shutdown(self):
        self.httpd.shutdown()
