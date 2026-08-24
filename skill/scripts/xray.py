#!/usr/bin/env python3
"""js-xray orchestrator: deobfuscate -> analyze -> report.

Usage:
    python3 scripts/xray.py <input.js> [-o OUTDIR] [--anchors anchors.json]
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))


def step(label, cmd):
    sys.stderr.write("[js-xray] %s\n" % label)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        sys.stderr.write(proc.stdout.rstrip() + "\n")
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.rstrip()[-2000:] + "\n")
        sys.stderr.write("[js-xray] step failed: %s\n" % label)
        return False
    if proc.stderr.strip():
        # non-fatal warnings from the wrapper
        for line in proc.stderr.strip().splitlines():
            if line.startswith("WARNING") or line.startswith("using node"):
                sys.stderr.write("  " + line + "\n")
    return True


def main():
    ap = argparse.ArgumentParser(description="js-xray: deobfuscate and analyze JavaScript")
    ap.add_argument("input")
    ap.add_argument("-o", "--outdir", help="output directory (default: xray_<name>/ next to input)")
    ap.add_argument("--anchors", help="custom anchors json")
    ap.add_argument("--skip-deobfuscate", action="store_true", help="analyze the input as-is")
    ap.add_argument("--mangle", action="store_true", help="pass --mangle to webcrack")
    ap.add_argument("--max-blocks", type=int, default=12)
    args = ap.parse_args()

    inp = os.path.abspath(args.input)
    if not os.path.isfile(inp):
        sys.stderr.write("no such file: %s\n" % inp)
        return 1

    stem = os.path.splitext(os.path.basename(inp))[0]
    outdir = os.path.abspath(args.outdir) if args.outdir else os.path.join(os.path.dirname(inp), "xray_" + stem)
    os.makedirs(outdir, exist_ok=True)

    clean = os.path.join(outdir, "clean.js")
    meta = os.path.join(outdir, "webcrack.json")
    log = os.path.join(outdir, "webcrack.log")
    analysis = os.path.join(outdir, "analysis.json")
    report_md = os.path.join(outdir, "report.md")

    if args.skip_deobfuscate:
        sys.stderr.write("[js-xray] 1/3 deobfuscate: skipped\n")
        with open(inp, encoding="utf-8", errors="replace") as fh:
            open(clean, "w").write(fh.read())
        meta_arg = []
    else:
        cmd = [sys.executable, os.path.join(HERE, "run_webcrack.py"), inp, clean, "--meta", meta, "--log", log]
        if args.mangle:
            cmd.append("--mangle")
        if not step("1/3 deobfuscate (webcrack)", cmd):
            return 1
        meta_arg = ["--meta", meta]

    cmd = [sys.executable, os.path.join(HERE, "analyze.py"), clean, analysis,
           "--max-blocks", str(args.max_blocks)]
    if args.anchors:
        cmd += ["--anchors", os.path.abspath(args.anchors)]
    if not step("2/3 analyze", cmd):
        return 1

    cmd = [sys.executable, os.path.join(HERE, "report.py"), analysis, report_md,
           "--source", inp, "--clean", clean] + meta_arg
    if not step("3/3 report", cmd):
        return 1

    sys.stderr.write("[js-xray] done\n")
    print(report_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
