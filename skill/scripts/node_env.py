#!/usr/bin/env python3
# Resolve a Node.js binary whose version satisfies webcrack's engine range.
# webcrack 2.16 requires: >=22 <23 || >=24 <25  (isolated-vm native ABI)
import json
import os
import re
import subprocess
import sys

SUPPORTED = ((22, 23), (24, 25))


def in_range(major):
    return any(lo <= major < hi for lo, hi in SUPPORTED)


def version_of(node_bin):
    try:
        out = subprocess.run([node_bin, "-v"], capture_output=True, text=True, timeout=20)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    m = re.match(r"v(\d+)\.(\d+)\.(\d+)", out.stdout.strip())
    if not m:
        return None
    return tuple(int(g) for g in m.groups())


def candidates():
    # 1. explicit override wins
    env_node = os.environ.get("JSXRAY_NODE")
    if env_node:
        yield env_node
    # 2. version managers, newest first
    homedir = os.path.expanduser("~")
    roots = [
        os.path.join(os.environ.get("FNM_DIR", os.path.join(homedir, ".local/share/fnm")), "node-versions"),
        os.path.join(homedir, "Library/Application Support/fnm/node-versions"),
        os.path.join(homedir, ".volta/tools/image/node"),
        os.path.join(homedir, ".nvm/versions/node"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root), reverse=True):
            for rel in ("installation/bin/node", "bin/node"):
                cand = os.path.join(root, name, rel)
                if os.path.isfile(cand):
                    yield cand
    # 3. whatever is on PATH
    yield "node"


def resolve():
    seen = set()
    for cand in candidates():
        if cand in seen:
            continue
        seen.add(cand)
        ver = version_of(cand)
        if ver and in_range(ver[0]):
            return cand, ver
    return None, None


def main():
    node_bin, ver = resolve()
    as_json = "--json" in sys.argv[1:]
    if not node_bin:
        msg = (
            "No Node.js in webcrack's supported range (>=22 <23 || >=24 <25).\n"
            "Install one, e.g.:  fnm install 24   (or volta install node@24)\n"
            "Or point JSXRAY_NODE at a compatible binary."
        )
        if as_json:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            sys.stderr.write(msg + "\n")
        return 1
    vstr = "v%d.%d.%d" % ver
    if as_json:
        print(json.dumps({"ok": True, "node": node_bin, "version": vstr}))
    else:
        print(node_bin)
        sys.stderr.write("using node %s (%s)\n" % (vstr, node_bin))
    return 0


if __name__ == "__main__":
    sys.exit(main())
