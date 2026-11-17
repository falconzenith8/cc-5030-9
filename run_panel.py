#!/usr/bin/env python3
"""Launch the multi-camera sync preview panel (CLI auxiliary entry).

Usage:
  python3 -I run_panel.py --pack demo_pack [--host 127.0.0.1] [--port 8765]
  python3 -I run_panel.py --config demo.json            # legacy mp4 sample
  python3 -I run_panel.py --pack demo_pack --render demo_pack/exports/run1 \
                          [--duration 12] [--fps 10]

Without --render the live panel starts; open the printed URL in any
browser (multiple clients may connect).  With --render a deterministic
PNG composite sequence, animated GIF and JSON frame-pick report are
produced instead.  The graphical entry is the browser panel; this CLI
only builds packs, runs verifications and launches the server.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from multicam import MultiCamApp, PanelServer, load_config, load_pack


def main():
    ap = argparse.ArgumentParser(description="multi-camera sync preview panel")
    ap.add_argument("--config", default="demo.json",
                    help="legacy JSON config (mp4 sources need PyAV)")
    ap.add_argument("--pack", help="self-made material pack directory")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--render", help="offline composite output directory")
    ap.add_argument("--duration", type=float, default=12.0)
    ap.add_argument("--fps", type=int, default=10)
    args = ap.parse_args()

    if args.pack:
        app = load_pack(args.pack)
    else:
        app = MultiCamApp(load_config(args.config))

    if args.render:
        print(f"[render] offline composite -> {args.render}")
        info = app.render_offline(args.render, args.duration, args.fps)
        print(f"[render] {info['frames']} frames written")
        print(f"[render] pick report: {info['report']}")
        if info["gif"]:
            print(f"[render] animated summary: {info['gif']}")
        for name, m in info["metrics"].items():
            print(f"  {name}: picks={m['picks']} stalls={m['stalls']} "
                  f"mean_err={m['mean_err_ms']:.1f}ms max_err={m['max_err_ms']:.1f}ms")
        return

    app.start()
    server = PanelServer(app, args.host, args.port)
    url = f"http://{args.host}:{args.port}/"
    print("=" * 60)
    print("  多机位同步预监面板已启动 / panel is running")
    print(f"  图形入口(浏览器) / graphical entry:  {url}")
    print("  多终端可同时连接；Ctrl-C 退出。")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()


if __name__ == "__main__":
    main()
