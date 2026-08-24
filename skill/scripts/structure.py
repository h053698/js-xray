#!/usr/bin/env python3
"""Run the AST structure extractor and return its facts as Python data.

structure.mjs needs Babel, which only exists in the repo-local node_modules, and
a Node in the version range webcrack pinned. Both are located the same way the
inlining pass does it, so a single environment fix covers every AST stage.

Failure is not fatal: the caller still has clean.js and the anchor pass. When the
extractor cannot run we emit an empty-but-valid structure so downstream stages do
not need to special-case a missing file.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from node_env import resolve  # noqa: E402
from inline_strings import find_node_modules  # noqa: E402

EXTRACTOR = os.path.join(HERE, "structure.mjs")

EMPTY = {
    "lines": 0,
    "bytes": 0,
    "functions": [],
    "classes": [],
    "call_graph": {"edges": [], "resolution": "unavailable"},
    "module": {"exports": [], "imports": [], "global_assignments": []},
    "literals": {"urls": [], "paths": []},
}


def extract(inp, out=None, timeout=600):
    """Return (structure_dict, error_or_None). Writes out when given."""
    node_bin, ver = resolve()
    if not node_bin:
        return _degrade(inp, out, "no compatible node found")
    if not os.path.isfile(EXTRACTOR):
        return _degrade(inp, out, "structure.mjs missing")

    env = dict(os.environ)
    node_modules = find_node_modules()
    if node_modules:
        existing = env.get("NODE_PATH")
        env["NODE_PATH"] = node_modules + (os.pathsep + existing if existing else "")

    target = os.path.abspath(out) if out else os.path.join(
        os.path.dirname(os.path.abspath(inp)), ".structure.tmp.json")
    cmd = [node_bin, EXTRACTOR, os.path.abspath(inp), target]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return _degrade(inp, out, "structure extraction timed out")

    if proc.returncode != 0 or not os.path.isfile(target):
        tail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "exit %s" % proc.returncode
        return _degrade(inp, out, "structure extraction failed: %s" % tail)

    try:
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        return _degrade(inp, out, "structure output unreadable: %s" % exc)
    finally:
        if not out:
            try:
                os.unlink(target)
            except OSError:
                pass

    data.setdefault("source_file", os.path.abspath(inp))
    data["node_version"] = "v%d.%d.%d" % ver
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    return data, None


def _degrade(inp, out, error):
    """Emit a valid empty structure so later stages keep a uniform contract."""
    data = json.loads(json.dumps(EMPTY))
    data["source_file"] = os.path.abspath(inp)
    data["error"] = error
    try:
        with open(inp, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        data["lines"] = text.count("\n") + 1
        data["bytes"] = len(text.encode("utf-8"))
    except OSError:
        pass
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    sys.stderr.write("WARNING: %s\n" % error)
    return data, error


def summarize(data):
    """One-line summary for pipeline logs."""
    if data.get("error"):
        return data["error"]
    return "%d functions, %d classes, %d call edges, %d urls" % (
        len(data.get("functions", [])),
        len(data.get("classes", [])),
        len(data.get("call_graph", {}).get("edges", [])),
        len(data.get("literals", {}).get("urls", [])),
    )


def main():
    ap = argparse.ArgumentParser(description="extract structural facts from a JS file")
    ap.add_argument("input")
    ap.add_argument("output")
    args = ap.parse_args()
    data, error = extract(args.input, args.output)
    print(summarize(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
