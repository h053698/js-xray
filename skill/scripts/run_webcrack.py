#!/usr/bin/env python3
# Run webcrack to inline string arrays and unminify, using a compatible Node.
import argparse
import json
import os
import shutil
import subprocess
import sys

# realpath so the script still finds node_modules when installed via symlink
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from node_env import resolve  # noqa: E402

# Repo-local install lives two levels up from skill/scripts/
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def find_webcrack_cli():
    """Locate webcrack's CLI. Prefers the pinned repo-local install."""
    bases = []
    env_home = os.environ.get("JSXRAY_HOME")
    if env_home:
        bases.append(env_home)
    bases += [REPO_ROOT, os.getcwd(), os.path.expanduser("~/dev/yuchan/js-xray")]
    for base in bases:
        cand = os.path.join(base, "node_modules", "webcrack", "dist", "cli.js")
        if os.path.isfile(cand):
            return cand
    return None


PARSE_KEYS = {
    "String Array": "string_array",
    "String Array Rotate": "rotate",
    "String Array Encoding": "encoding",
    "String Array Decoders": "decoders",
}


def parse_log(log):
    info = {}
    changes = {}
    for line in log.splitlines():
        for key, slug in PARSE_KEYS.items():
            marker = "deobfuscate " + key + ": "
            if marker in line:
                info[slug] = line.split(marker, 1)[1].strip()
        if ": finished with " in line and "transforms " in line:
            stage = line.split("transforms ", 1)[1].split(":", 1)[0]
            try:
                n = int(line.split("finished with ", 1)[1].split(" ", 1)[0])
            except (ValueError, IndexError):
                continue
            changes[stage] = n
    info["changes"] = changes
    info["deobfuscated"] = info.get("string_array", "no") != "no"
    return info


def main():
    ap = argparse.ArgumentParser(description="webcrack wrapper")
    ap.add_argument("input")
    ap.add_argument("output", help="output .js path")
    ap.add_argument("--log", help="path to write raw webcrack log")
    ap.add_argument("--meta", help="path to write parsed metadata json")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--mangle", action="store_true")
    args = ap.parse_args()

    node_bin, ver = resolve()
    cli = find_webcrack_cli()
    meta = {"ok": False, "node": node_bin, "webcrack_cli": cli}

    if not node_bin or not cli:
        meta["error"] = (
            "missing compatible node" if not node_bin else "webcrack not installed (run: bun install)"
        )
        # Degrade gracefully: analysis can still run on the raw source.
        shutil.copyfile(args.input, args.output)
        meta["fallback"] = "copied source unchanged"
        if args.meta:
            open(args.meta, "w").write(json.dumps(meta, indent=2))
        sys.stderr.write("WARNING: %s -> analyzing raw source\n" % meta["error"])
        return 0

    meta["node_version"] = "v%d.%d.%d" % ver
    cmd = [node_bin, cli, os.path.abspath(args.input)]
    if args.mangle:
        cmd.append("--mangle")
    env = dict(os.environ, DEBUG="webcrack:*")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout, env=env)
    except subprocess.TimeoutExpired:
        shutil.copyfile(args.input, args.output)
        meta["error"] = "webcrack timed out after %ss" % args.timeout
        meta["fallback"] = "copied source unchanged"
        if args.meta:
            open(args.meta, "w").write(json.dumps(meta, indent=2))
        sys.stderr.write("WARNING: %s\n" % meta["error"])
        return 0

    # webcrack prints code on stdout, debug log on stderr
    code = proc.stdout
    log = proc.stderr
    if proc.returncode != 0 or not code.strip():
        shutil.copyfile(args.input, args.output)
        meta["error"] = "webcrack failed (exit %s)" % proc.returncode
        meta["stderr_tail"] = log[-1500:]
        meta["fallback"] = "copied source unchanged"
        sys.stderr.write("WARNING: %s -> analyzing raw source\n" % meta["error"])
    else:
        open(args.output, "w").write(code)
        meta.update(parse_log(log))
        meta["ok"] = True
        meta["in_bytes"] = os.path.getsize(args.input)
        meta["out_bytes"] = os.path.getsize(args.output)

    if args.log:
        open(args.log, "w").write(log)
    if args.meta:
        open(args.meta, "w").write(json.dumps(meta, indent=2))
    print(json.dumps({k: v for k, v in meta.items() if k != "stderr_tail"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
