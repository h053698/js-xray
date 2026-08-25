#!/usr/bin/env python3
"""Control-flow deflattening pass: the stage that makes clean.js worth reading.

webcrack already unflattens javascript-obfuscator's switch dispatchers and its
always-true/always-false branches -- but only when the deciding value is a
literal sitting in the expression. The obfuscator usually routes it through a
per-function "control flow storage" object first:

    const S = {VJuTL: "QkPnV", JsWMV: "4|5|1|3|0|2",
               YqrfQ: function (a, b) { return a === b; }};
    if (S.YqrfQ(S.VJuTL, S.VJuTL)) { dead } else { live }
    var seq = S.JsWMV.split("|");

webcrack inlines that object first and its two passes then fire. When the
inlining bails -- the object escapes, a property is written, a key is dynamic --
the object survives and both downstream passes quietly stop matching, so what
lands in clean.js has every string decoded and half its lines unreachable. That
is the file a reader then spends most of their tokens on. This stage resolves the
deciding value through the storage object and finishes the job.

The transform itself runs on Babel's AST in deflatten.mjs, for the same reason
the inlining pass does: deciding whether two operands are the same value, or
whether a case body can be moved, needs real scope bindings. This module locates
a compatible Node, runs it, and gates the result.

On the gate: `node --check` is here for parity with the inlining pass, but it is
much weaker protection than it is there. A wrong decision in this pass -- the
live branch dropped instead of the dead one, or independent-looking cases
reordered when they were not -- yields a file that is still perfectly valid
JavaScript. Syntax checking cannot see it, and neither can any later stage; they
would go on to explain code that never ran. The real safety therefore lives in
deflatten.mjs, which refuses every construct it cannot prove, and in the
execution-equivalence test in tests/test_xray.py, which runs the before and after
files under node and compares their output. Refusals are counted in the meta
(`dead_branch_skips`, `switch_skips`) so a partial result reads as partial.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

# realpath so the script still finds its .mjs sibling when installed via symlink
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from node_env import resolve  # noqa: E402
from inline_strings import find_node_modules, node_syntax_check  # noqa: E402

TRANSFORM = os.path.join(HERE, "deflatten.mjs")


def deflatten_file(inp, out, meta_path=None, node_check=True):
    """Run the AST pass. Falls back to copying the input on any failure."""
    node_bin, ver = resolve()
    meta = {
        "ok": False,
        "node": node_bin,
        "dead_branches_dropped": 0,
        "switch_sequences_linearised": 0,
        "rolled_back": False,
    }

    if not node_bin or not os.path.isfile(TRANSFORM):
        meta["error"] = "no compatible node" if not node_bin else "deflatten.mjs missing"
        meta["fallback"] = "copied input unchanged"
        shutil.copyfile(inp, out)
        _write_meta(meta_path, meta)
        sys.stderr.write("WARNING: %s -> skipping deflatten pass\n" % meta["error"])
        return 0, meta

    meta["node_version"] = "v%d.%d.%d" % ver
    env = dict(os.environ)
    node_modules = find_node_modules()
    if node_modules:
        # let the transform resolve @babel/* from the repo-local install
        existing = env.get("NODE_PATH")
        env["NODE_PATH"] = node_modules + (os.pathsep + existing if existing else "")

    tmp_meta = out + ".deflatten.json"
    cmd = [node_bin, TRANSFORM, os.path.abspath(inp), os.path.abspath(out), tmp_meta]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    except subprocess.TimeoutExpired:
        shutil.copyfile(inp, out)
        meta["error"] = "deflatten transform timed out"
        meta["fallback"] = "copied input unchanged"
        _write_meta(meta_path, meta)
        sys.stderr.write("WARNING: %s\n" % meta["error"])
        return 0, meta

    if os.path.isfile(tmp_meta):
        try:
            meta.update(json.load(open(tmp_meta)))
        except Exception:
            pass
        try:
            os.unlink(tmp_meta)
        except OSError:
            pass

    if proc.returncode not in (0, 4) or not os.path.isfile(out):
        shutil.copyfile(inp, out)
        meta["error"] = "deflatten transform failed (exit %s)" % proc.returncode
        meta["stderr_tail"] = proc.stderr[-1000:]
        meta["fallback"] = "copied input unchanged"
        _write_meta(meta_path, meta)
        sys.stderr.write("WARNING: %s -> skipping deflatten pass\n" % meta["error"])
        return 0, meta

    if proc.returncode == 4:
        # transform already rolled back to the input; surface why
        meta["rolled_back"] = True
        sys.stderr.write("WARNING: deflatten produced invalid syntax, rolled back\n")
    elif node_check:
        ok, detail = node_syntax_check(node_bin, out)
        meta["node_check"] = "ok" if ok else detail
        if not ok:
            shutil.copyfile(inp, out)
            meta["rolled_back"] = True
            meta["error"] = "node --check rejected output: %s" % detail
            sys.stderr.write("WARNING: %s -> rolled back\n" % meta["error"])

    meta["ok"] = not meta["rolled_back"]
    meta["in_bytes"] = os.path.getsize(inp)
    meta["out_bytes"] = os.path.getsize(out)
    _write_meta(meta_path, meta)
    return 0, meta


def _write_meta(path, meta):
    if path:
        open(path, "w").write(json.dumps(meta, indent=2))


def summarize(meta):
    """Compact one-line summary for pipeline logs."""
    if meta.get("rolled_back"):
        return "rolled back (%s)" % meta.get("error", meta.get("parse_error", "invalid output"))
    if not meta.get("ok"):
        return meta.get("error", "skipped")
    before = meta.get("lines_before")
    after = meta.get("lines_after")
    span = ""
    if before and after and after != before:
        span = ", %d -> %d lines" % (before, after)
    skipped = len(meta.get("switch_skips", {}) or {}) + len(meta.get("dead_branch_skips", {}) or {})
    tail = ", %d construct(s) left alone" % skipped if skipped else ""
    return "%d dead branches dropped, %d switch sequences linearised%s%s" % (
        meta.get("dead_branches_dropped", 0),
        meta.get("switch_sequences_linearised", 0),
        span,
        tail,
    )


def main():
    ap = argparse.ArgumentParser(
        description="unflatten control-flow residue javascript-obfuscator leaves behind (AST-based)")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--meta")
    ap.add_argument("--no-node-check", action="store_true", help="skip the `node --check` gate")
    args = ap.parse_args()

    rc, meta = deflatten_file(args.input, args.output, args.meta,
                              node_check=not args.no_node_check)
    trimmed = {k: v for k, v in meta.items() if k not in ("stderr_tail",)}
    print(json.dumps(trimmed, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
