#!/usr/bin/env python3
"""js-xray orchestrator: deobfuscate -> inline -> structure -> explain -> report.

Usage:
    python3 scripts/xray.py <input.js> [-o OUTDIR] [--anchors anchors.json]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)


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
    ap.add_argument("--skip-inline", action="store_true", help="skip the second-pass string inlining")
    ap.add_argument("--mangle", action="store_true", help="pass --mangle to webcrack")
    ap.add_argument("--skip-anchors", action="store_true",
                    help="skip the keyword anchor pass and its markdown report input")
    ap.add_argument("--top", type=int, default=25,
                    help="how many functions to detail in xray.json")
    ap.add_argument("--max-blocks", type=int, default=12)
    args = ap.parse_args()

    inp = os.path.abspath(args.input)
    if not os.path.isfile(inp):
        sys.stderr.write("no such file: %s\n" % inp)
        return 1

    stem = os.path.splitext(os.path.basename(inp))[0]
    outdir = os.path.abspath(args.outdir) if args.outdir else os.path.join(os.path.dirname(inp), "xray_" + stem)
    os.makedirs(outdir, exist_ok=True)

    pass1 = os.path.join(outdir, "webcrack.js")
    clean = os.path.join(outdir, "clean.js")
    meta = os.path.join(outdir, "webcrack.json")
    log = os.path.join(outdir, "webcrack.log")
    inline_meta = os.path.join(outdir, "inline.json")
    analysis = os.path.join(outdir, "analysis.json")
    structure_json = os.path.join(outdir, "structure.json")
    explanation = os.path.join(outdir, "xray.json")
    report_md = os.path.join(outdir, "report.md")

    total = (5 if args.skip_inline else 6) - (1 if args.skip_anchors else 0)
    n = 0

    n += 1
    if args.skip_deobfuscate:
        sys.stderr.write("[js-xray] %d/%d deobfuscate: skipped\n" % (n, total))
        with open(inp, encoding="utf-8", errors="replace") as fh:
            open(pass1, "w").write(fh.read())
        meta_arg = []
    else:
        cmd = [sys.executable, os.path.join(HERE, "run_webcrack.py"), inp, pass1, "--meta", meta, "--log", log]
        if args.mangle:
            cmd.append("--mangle")
        if not step("%d/%d deobfuscate (webcrack)" % (n, total), cmd):
            return 1
        meta_arg = ["--meta", meta]

    # Second pass: resolve per-scope string arrays webcrack left behind. Rolls
    # itself back to the first-pass output if the rewrite would not parse.
    inline_arg = []
    if args.skip_inline:
        shutil.copyfile(pass1, clean)
    else:
        n += 1
        cmd = [sys.executable, os.path.join(HERE, "inline_strings.py"), pass1, clean, "--meta", inline_meta]
        if not step("%d/%d inline residual strings" % (n, total), cmd):
            return 1
        if os.path.isfile(inline_meta):
            inline_arg = ["--inline-meta", inline_meta]
            try:
                import inline_strings
                sys.stderr.write("  " + inline_strings.summarize(json.load(open(inline_meta))) + "\n")
            except Exception:
                pass

    # Structure and explanation are the products an agent consumes. The anchor
    # pass stays because it is the one place a user can inject domain keywords,
    # but it is no longer what drives the report.
    n += 1
    cmd = [sys.executable, os.path.join(HERE, "structure.py"), clean, structure_json]
    if not step("%d/%d extract structure" % (n, total), cmd):
        return 1

    n += 1
    cmd = [sys.executable, os.path.join(HERE, "explain.py"), structure_json, explanation,
           "--top", str(args.top)] + inline_arg
    if not step("%d/%d explain" % (n, total), cmd):
        return 1

    analysis_arg = []
    if not args.skip_anchors:
        n += 1
        cmd = [sys.executable, os.path.join(HERE, "analyze.py"), clean, analysis,
               "--max-blocks", str(args.max_blocks)]
        if args.anchors:
            cmd += ["--anchors", os.path.abspath(args.anchors)]
        if not step("%d/%d anchor scan" % (n, total), cmd):
            return 1
        analysis_arg = ["--analysis", analysis]

    n += 1
    cmd = [sys.executable, os.path.join(HERE, "report.py"), explanation, report_md,
           "--source", inp, "--clean", clean] + analysis_arg + meta_arg + inline_arg
    if not step("%d/%d report" % (n, total), cmd):
        return 1

    sys.stderr.write("[js-xray] done\n")
    print(explanation)
    return 0


if __name__ == "__main__":
    sys.exit(main())
