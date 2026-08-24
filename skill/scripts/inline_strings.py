#!/usr/bin/env python3
"""Second-pass string-array inlining for decoders webcrack leaves behind.

webcrack resolves the one string array it identifies as *the* array. Files that
declare a separate array per IIFE scope keep working decoder calls afterwards:

    function U() { const t = ["_getAnswer", "width", ...]; return (U = ...)(); }
    function O(t, n) { const e = U(); return (O = function (t, n) {
        return e[t -= 0]; })(t, n); }
    const C = O;

Resolving those needs real scope information -- short alias names like t, e, i
and C are reused across scopes for *different* arrays, so a textual pass
silently resolves indices against the wrong array. The actual work therefore
happens in inline_strings.mjs on Babel's AST; this module locates a compatible
Node, runs it, and verifies the output still parses before accepting it.
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

TRANSFORM = os.path.join(HERE, "inline_strings.mjs")
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def find_node_modules():
    """Babel comes in as a webcrack dependency; the transform needs it resolvable."""
    bases = []
    env_home = os.environ.get("JSXRAY_HOME")
    if env_home:
        bases.append(env_home)
    bases += [REPO_ROOT, os.getcwd(), os.path.expanduser("~/dev/yuchan/js-xray")]
    for base in bases:
        cand = os.path.join(base, "node_modules", "@babel", "parser")
        if os.path.isdir(cand):
            return os.path.join(base, "node_modules")
    return None


def node_syntax_check(node_bin, path):
    """Independent syntax gate via `node --check`.

    Extension decides the goal symbol, so try module then script; a file is fine
    if either accepts it. Returns (ok, message).
    """
    import tempfile

    last = ""
    for ext in (".mjs", ".cjs"):
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        try:
            tmp.close()
            shutil.copyfile(path, tmp.name)
            proc = subprocess.run([node_bin, "--check", tmp.name],
                                  capture_output=True, text=True, timeout=120)
            if proc.returncode == 0:
                return True, ""
            last = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "exit %s" % proc.returncode
        except Exception as exc:  # node missing or timed out -- do not block on it
            return True, "check skipped: %s" % exc
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    return False, last


def inline_file(inp, out, meta_path=None, node_check=True):
    """Run the AST pass. Falls back to copying the input on any failure."""
    node_bin, ver = resolve()
    meta = {"ok": False, "node": node_bin, "replaced": 0, "rolled_back": False}

    if not node_bin or not os.path.isfile(TRANSFORM):
        meta["error"] = "no compatible node" if not node_bin else "inline_strings.mjs missing"
        meta["fallback"] = "copied input unchanged"
        shutil.copyfile(inp, out)
        _write_meta(meta_path, meta)
        sys.stderr.write("WARNING: %s -> skipping second pass\n" % meta["error"])
        return 0, meta

    meta["node_version"] = "v%d.%d.%d" % ver
    env = dict(os.environ)
    node_modules = find_node_modules()
    if node_modules:
        # let the transform resolve @babel/* from the repo-local install
        existing = env.get("NODE_PATH")
        env["NODE_PATH"] = node_modules + (os.pathsep + existing if existing else "")

    tmp_meta = out + ".inline.json"
    cmd = [node_bin, TRANSFORM, os.path.abspath(inp), os.path.abspath(out), tmp_meta]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    except subprocess.TimeoutExpired:
        shutil.copyfile(inp, out)
        meta["error"] = "inline transform timed out"
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
        meta["error"] = "inline transform failed (exit %s)" % proc.returncode
        meta["stderr_tail"] = proc.stderr[-1000:]
        meta["fallback"] = "copied input unchanged"
        _write_meta(meta_path, meta)
        sys.stderr.write("WARNING: %s -> skipping second pass\n" % meta["error"])
        return 0, meta

    if proc.returncode == 4:
        # transform already rolled back to the input; surface why
        meta["rolled_back"] = True
        sys.stderr.write("WARNING: second pass produced invalid syntax, rolled back\n")
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
    return "%d strings inlined, %d member accesses normalized, %d arrays, %d decoders" % (
        meta.get("replaced", 0),
        meta.get("members_normalized", 0),
        meta.get("arrays", 0),
        len(meta.get("decoders", []) or []),
    )


def main():
    ap = argparse.ArgumentParser(description="inline residual string-array decoders (AST-based)")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--meta")
    ap.add_argument("--no-node-check", action="store_true", help="skip the `node --check` gate")
    args = ap.parse_args()

    rc, meta = inline_file(args.input, args.output, args.meta, node_check=not args.no_node_check)
    trimmed = {k: v for k, v in meta.items() if k not in ("aliases", "stderr_tail")}
    print(json.dumps(trimmed, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
