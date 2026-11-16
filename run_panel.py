#!/usr/bin/env python3
"""Launch the multi-camera sync preview panel.

Usage:
  python3 run_panel.py [--config demo.json] [--host 127.0.0.1] [--port 8765]
                       [--render out/composite.mp4 [--duration 6 --fps 30]]

Without --render the live panel starts; open the printed URL in any
browser (multiple clients may connect).  With --render a deterministic
composite mp4 plus a JSON frame-pick report are produced instead.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from multicam import MultiCamApp, PanelServer, load_config


def main():
    ap = argparse.ArgumentParser(description="multi-camera sync preview panel")
    ap.add_argument("--config", default="demo.json")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--render", help="offline composite output mp4 path")
    ap.add_argument("--duration", type=float, default=6.0)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    config = load_config(args.config)
    app = MultiCamApp(config)

    if args.render:
        print(f"[render] offline composite -> {args.render}")
        info = app.render_offline(args.render, args.duration, args.fps)
        print(f"[render] {info['frames']} frames written")
        print(f"[render] pick report: {info['report']}")
        for name, m in info["metrics"].items():
            print(f"  {name}: picks={m['picks']} stalls={m['stalls']} "
                  f"mean_err={m['mean_err_ms']:.1f}ms max_err={m['max_err_ms']:.1f}ms")
        return

    app.start()
    server = PanelServer(app, args.host, args.port)
    url = f"http://{args.host}:{args.port}/"
    print("=" * 60)
    print("  多机位同步预监面板已启动 / panel is running")
    print(f"  在浏览器打开 / open in a browser:  {url}")
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
