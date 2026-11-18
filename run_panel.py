#!/usr/bin/env python3
"""Launch the multi-camera sync preview panel.

Graphical entry (the normal way to use the preview):

  python3 run_panel.py                      # panel; pick/load a project in the page
  python3 run_panel.py --project sync_demo  # panel pre-loaded with the sync package
  python3 run_panel.py --config demo.json   # legacy constant-fps demo

The page lists every project package under --package-roots and loads it
through the strict loader (a broken package is rejected, not replaced by
defaults).  Multiple browser clients may connect at once.

Command line is only an auxiliary/offline helper:

  python3 run_panel.py --project sync_demo --render out/sync_composite.mp4 \
      --duration 14 --fps 10
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from multicam import MultiCamApp, PanelServer, load_config, load_project


def build_app(args):
    if args.project:
        config, meta = load_project(args.project)
        print(f"[panel] loaded project package: {meta['name']} "
              f"({len(config['streams'])} streams)")
        if args.render:
            args.duration = meta["timeline_duration_s"] or args.duration
        return config
    return load_config(args.config)


def main():
    ap = argparse.ArgumentParser(description="multi-camera sync preview panel")
    ap.add_argument("--config", default="demo.json",
                    help="legacy loose config (default: demo.json)")
    ap.add_argument("--project", help="strict preview project package directory")
    ap.add_argument("--package-roots", default=".",
                    help="comma-separated roots the page may load projects from")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--workdir", default="out")
    ap.add_argument("--render", help="offline composite output mp4 path")
    ap.add_argument("--duration", type=float, default=6.0)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    config = build_app(args)
    app = MultiCamApp(config, workdir=args.workdir)
    roots = [r for r in args.package_roots.split(",") if r]

    if args.render:
        print(f"[render] offline composite -> {args.render}")
        info = app.render_offline(args.render, args.duration, args.fps)
        print(f"[render] {info['frames']} frames written")
        print(f"[render] pick report: {info['report']}")
        for name, m in info["metrics"].items():
            print(f"  {name}: picks={m['picks']} stalls={m['stalls']} "
                  f"gaps={m['gaps']} mean_err={m['mean_err_ms']:.1f}ms "
                  f"max_err={m['max_err_ms']:.1f}ms")
        return

    app.start()
    server = PanelServer(app, args.host, args.port, package_roots=roots,
                         workdir=os.path.join(args.workdir, "live_projects"))
    url = f"http://{args.host}:{args.port}/"
    print("=" * 64)
    print("  多机位同步预监面板已启动 / panel is running")
    print(f"  图形入口 / graphical entry:  {url}")
    print("  在页面顶部“预监工程包”下拉框选择并载入；多终端可同时连接。")
    print("  Ctrl-C 退出。")
    print("=" * 64)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()


if __name__ == "__main__":
    main()
