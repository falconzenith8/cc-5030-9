"""Strict loader for multi-camera preview project packages.

A project package is a directory containing ``project.json``, its media
files and (for the sync-demo material) ``ground_truth.json``.  Loading is
strict on purpose: a missing key, an unknown schema, a dangling media
path or an invalid gap interval fails loudly with a ProjectError instead
of being papered over by a default value.  That is what keeps a broken
package from silently presenting fabricated "multi-camera" pictures.
"""
import json
import os

PROJECT_SCHEMA = "multicam-preview-project/2"
POLICIES = ("nearest", "hold")
ON_STALL = ("hold", "blank")

REQUIRED_TOP_KEYS = (
    "schema", "name", "streams", "policy", "reference",
    "wait_budget_ms", "on_stall", "continue_others_on_stall",
)
REQUIRED_STREAM_KEYS = ("name", "path", "offset")


class ProjectError(Exception):
    pass


def _require(cond, msg):
    if not cond:
        raise ProjectError(msg)


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_project(path):
    """Load ``project.json`` (or a package directory containing it).

    Returns ``(config, meta)`` where ``config`` is the dict consumed by
    :class:`multicam.app.MultiCamApp` (media paths resolved to absolute)
    and ``meta`` records the package directory and ground-truth path.
    """
    if os.path.isdir(path):
        pkg_dir = os.path.abspath(path)
        proj_path = os.path.join(pkg_dir, "project.json")
    else:
        proj_path = os.path.abspath(path)
        pkg_dir = os.path.dirname(proj_path)
    _require(os.path.isfile(proj_path), f"project file not found: {proj_path}")
    try:
        with open(proj_path) as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ProjectError(f"invalid JSON in {proj_path}: {exc}") from exc
    _require(isinstance(data, dict), "project.json must contain an object")

    _require(data.get("schema") == PROJECT_SCHEMA,
             f"unsupported schema {data.get('schema')!r}; expected {PROJECT_SCHEMA}")
    for key in REQUIRED_TOP_KEYS:
        _require(key in data, f"project.json missing required key: {key}")

    _require(data["policy"] in POLICIES,
             f"policy must be one of {POLICIES}, got {data['policy']!r}")
    _require(data["on_stall"] in ON_STALL,
             f"on_stall must be one of {ON_STALL}, got {data['on_stall']!r}")
    _require(_is_number(data["wait_budget_ms"]) and data["wait_budget_ms"] >= 0,
             "wait_budget_ms must be a non-negative number")
    _require(isinstance(data["continue_others_on_stall"], bool),
             "continue_others_on_stall must be boolean")

    streams = data["streams"]
    _require(isinstance(streams, list) and streams,
             "streams must be a non-empty list")
    names = set()
    out_streams = []
    for i, s in enumerate(streams):
        _require(isinstance(s, dict), f"stream #{i} must be an object")
        for key in REQUIRED_STREAM_KEYS:
            _require(key in s, f"stream #{i} missing required key: {key}")
        name = s["name"]
        _require(isinstance(name, str) and name not in names,
                 f"duplicate or invalid stream name: {name!r}")
        names.add(name)
        _require(_is_number(s["offset"]), f"stream {name}: offset must be a number")
        media_path = os.path.normpath(os.path.join(pkg_dir, s["path"]))
        _require(os.path.isfile(media_path),
                 f"stream {name}: media file missing: {media_path}")

        gaps = []
        for g in s.get("gaps", []):
            _require(isinstance(g, (list, tuple)) and len(g) == 2
                     and _is_number(g[0]) and _is_number(g[1]) and g[0] < g[1],
                     f"stream {name}: gap must be [lo, hi] with lo < hi, got {g!r}")
            # gaps are declared and evaluated on the production timeline T
            gaps.append((float(g[0]), float(g[1])))

        stream_out = dict(s)
        stream_out["path"] = media_path
        stream_out["gaps"] = tuple(gaps)
        if "gap_error_s" in s:
            _require(_is_number(s["gap_error_s"]) and s["gap_error_s"] > 0,
                     f"stream {name}: gap_error_s must be a positive number")
        out_streams.append(stream_out)

    reference = data["reference"]
    _require(reference == "virtual" or reference in names,
             f"reference {reference!r} is not 'virtual' nor a stream name")
    if data.get("audio_source") not in (None, "mute"):
        _require(data["audio_source"] in names,
                 f"audio_source {data['audio_source']!r} is not a stream name")

    gap_error_ms = data.get("gap_error_ms")
    if gap_error_ms is not None:
        _require(_is_number(gap_error_ms) and gap_error_ms > 0,
                 "gap_error_ms must be a positive number")

    gt_rel = data.get("ground_truth")
    gt_path = None
    if gt_rel:
        gt_path = os.path.normpath(os.path.join(pkg_dir, gt_rel))
        _require(os.path.isfile(gt_path),
                 f"declared ground truth missing: {gt_path}")

    config = {
        "streams": out_streams,
        "policy": data["policy"],
        "reference": reference,
        "audio_source": data.get("audio_source"),
        "wait_budget_ms": data["wait_budget_ms"],
        "speed": data.get("speed", 1.0),
        "on_stall": data["on_stall"],
        "continue_others_on_stall": data["continue_others_on_stall"],
        "simulate_decode_delay": data.get("simulate_decode_delay", {}),
    }
    if gap_error_ms is not None:
        config["gap_error_ms"] = gap_error_ms
    meta = {"package_dir": pkg_dir,
            "project_file": proj_path,
            "ground_truth": gt_path,
            "name": data["name"],
            "timeline_duration_s": data.get("timeline_duration_s")}
    return config, meta


def list_packages(roots):
    """Find package directories (those containing project.json)."""
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if "project.json" in filenames:
                found.append(os.path.abspath(dirpath))
                dirnames[:] = []
    return sorted(set(found))
