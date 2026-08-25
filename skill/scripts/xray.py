#!/usr/bin/env python3
"""js-xray orchestrator: deobfuscate -> inline -> deflatten -> structure -> explain -> report.

Usage:
    python3 scripts/xray.py <input.js> [-o OUTDIR] [--anchors anchors.json]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)


def step(label, cmd, n=None, total=None, record=None):
    """Run one pipeline stage, log it to stderr as before, and append a record
    of what happened to `record` (if given) so main() can write pipeline.json
    even when a later stage never runs.

    The record captures whatever JSON metadata the stage itself printed to
    stdout -- some stages print JSON (run_webcrack.py, inline_strings.py,
    analyze.py), others print a one-line human summary (structure.py,
    explain.py) or nothing at all (report.py just echoes its output path,
    toon_stats.py writes its stats to a separate file). Both cases are
    recorded: JSON parses into `meta` as a dict, anything else is kept as the
    raw stdout string (or None if the stage printed nothing).
    """
    sys.stderr.write("[js-xray] %s\n" % label)
    started = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    duration_s = round(time.monotonic() - started, 3)
    if proc.stdout.strip():
        sys.stderr.write(proc.stdout.rstrip() + "\n")
    ok = proc.returncode == 0
    if not ok:
        sys.stderr.write(proc.stderr.rstrip()[-2000:] + "\n")
        sys.stderr.write("[js-xray] step failed: %s\n" % label)
    elif proc.stderr.strip():
        # non-fatal warnings from the wrapper
        for line in proc.stderr.strip().splitlines():
            if line.startswith("WARNING") or line.startswith("using node"):
                sys.stderr.write("  " + line + "\n")

    if record is not None:
        stdout = proc.stdout.strip()
        try:
            meta = json.loads(stdout) if stdout else None
        except ValueError:
            meta = stdout or None
        record.append({
            "n": n,
            "total": total,
            "label": label,
            "cmd": list(cmd),
            "ok": ok,
            "meta": meta,
            "duration_s": duration_s,
        })
    return ok


def write_pipeline_log(outdir, inp, stages):
    """Write outdir/pipeline.json: the per-stage run log an agent can read
    instead of scrolling stderr. Written even after a stage failed and the
    run stopped short, so a failed stage is visible in pipeline.json rather
    than only on stderr (API-003)."""
    payload = {
        "schema": "js-xray/pipeline/1",
        "input": inp,
        "stages": stages,
    }
    path = os.path.join(outdir, "pipeline.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    return path


def main():
    ap = argparse.ArgumentParser(description="js-xray: deobfuscate and analyze JavaScript")
    ap.add_argument("input")
    ap.add_argument("-o", "--outdir", help="output directory (default: <name>.xrayjs/ next to input)")
    ap.add_argument("--anchors", help="custom anchors json")
    ap.add_argument("--skip-deobfuscate", action="store_true", help="analyze the input as-is")
    ap.add_argument("--skip-inline", action="store_true", help="skip the second-pass string inlining")
    ap.add_argument("--skip-deflatten", action="store_true",
                    help="skip the control-flow deflattening pass")
    ap.add_argument("--mangle", action="store_true", help="pass --mangle to webcrack")
    ap.add_argument("--skip-anchors", action="store_true",
                    help="skip the keyword anchor pass")
    ap.add_argument("--top", type=int, default=25,
                    help="how many functions to detail in xray.json")
    ap.add_argument("--max-blocks", type=int, default=12)
    args = ap.parse_args()

    inp = os.path.abspath(args.input)
    if not os.path.isfile(inp):
        sys.stderr.write("no such file: %s\n" % inp)
        return 1

    stem = os.path.splitext(os.path.basename(inp))[0]
    outdir = os.path.abspath(args.outdir) if args.outdir else os.path.join(os.path.dirname(inp), stem + ".xrayjs")
    os.makedirs(outdir, exist_ok=True)

    stages = []

    def fail(label=None):
        write_pipeline_log(outdir, inp, stages)
        return 1

    pass1 = os.path.join(outdir, "webcrack.js")
    pass2 = os.path.join(outdir, "inline.js")
    clean = os.path.join(outdir, "clean.js")
    meta = os.path.join(outdir, "webcrack.json")
    log = os.path.join(outdir, "webcrack.log")
    inline_meta = os.path.join(outdir, "inline.json")
    deflatten_meta = os.path.join(outdir, "deflatten.json")
    analysis = os.path.join(outdir, "analysis.json")
    structure_json = os.path.join(outdir, "structure.json")
    explanation = os.path.join(outdir, "xray.json")
    report_md = os.path.join(outdir, "report.md")
    toon_path = os.path.join(outdir, "xray.toon")
    toon_stats = os.path.join(outdir, "toon_stats.json")

    # TOON encoding always runs -- REQ-002 calls for it to ship on every run,
    # not behind a flag.
    total = 6 + (0 if args.skip_inline else 1) + (0 if args.skip_deflatten else 1) \
        - (1 if args.skip_anchors else 0)
    n = 0

    n += 1
    if args.skip_deobfuscate:
        label = "%d/%d deobfuscate: skipped" % (n, total)
        sys.stderr.write("[js-xray] %s\n" % label)
        with open(inp, encoding="utf-8", errors="replace") as fh:
            open(pass1, "w").write(fh.read())
        meta_arg = []
        stages.append({"n": n, "total": total, "label": label, "cmd": None,
                        "ok": True, "meta": None, "duration_s": 0.0})
    else:
        cmd = [sys.executable, os.path.join(HERE, "run_webcrack.py"), inp, pass1, "--meta", meta, "--log", log]
        if args.mangle:
            cmd.append("--mangle")
        label = "%d/%d deobfuscate (webcrack)" % (n, total)
        if not step(label, cmd, n=n, total=total, record=stages):
            return fail(label)
        meta_arg = ["--meta", meta]

    # Second pass: resolve per-scope string arrays webcrack left behind. Rolls
    # itself back to the first-pass output if the rewrite would not parse.
    #
    # This pass writes inline.js rather than clean.js, because the deflatten
    # stage below consumes its output and clean.js is whatever the last source
    # rewrite produced. When deflatten is skipped, inline.js is copied to
    # clean.js so downstream stages always read the same filename.
    inline_arg = []
    if args.skip_inline:
        shutil.copyfile(pass1, pass2)
    else:
        n += 1
        cmd = [sys.executable, os.path.join(HERE, "inline_strings.py"), pass1, pass2,
               "--meta", inline_meta]
        label = "%d/%d inline residual strings" % (n, total)
        if not step(label, cmd, n=n, total=total, record=stages):
            return fail(label)
        if os.path.isfile(inline_meta):
            inline_arg = ["--inline-meta", inline_meta]
            try:
                import inline_strings
                sys.stderr.write("  " + inline_strings.summarize(json.load(open(inline_meta))) + "\n")
            except Exception:
                pass

    # Third pass: unflatten the control-flow residue that survives webcrack --
    # always-decidable branches and split-sequence switch dispatchers whose
    # deciding value reaches them through a control-flow storage object rather
    # than as a literal. Without this the file is readable but half of it is
    # unreachable, which is where a reader's tokens go. Like the inline pass it
    # rolls back to its input rather than hand downstream a broken file, and it
    # refuses any construct it cannot prove safe rather than guessing (RSK-004).
    if args.skip_deflatten:
        shutil.copyfile(pass2, clean)
    else:
        n += 1
        cmd = [sys.executable, os.path.join(HERE, "deflatten.py"), pass2, clean,
               "--meta", deflatten_meta]
        label = "%d/%d deflatten control flow" % (n, total)
        if not step(label, cmd, n=n, total=total, record=stages):
            return fail(label)
        if os.path.isfile(deflatten_meta):
            try:
                import deflatten
                sys.stderr.write("  " + deflatten.summarize(json.load(open(deflatten_meta))) + "\n")
            except Exception:
                pass

    # Structure and explanation are the products an agent consumes. The anchor
    # pass stays because it is the one place a user can inject domain keywords,
    # but it is no longer what drives the report.
    n += 1
    cmd = [sys.executable, os.path.join(HERE, "structure.py"), clean, structure_json]
    label = "%d/%d extract structure" % (n, total)
    if not step(label, cmd, n=n, total=total, record=stages):
        return fail(label)

    n += 1
    cmd = [sys.executable, os.path.join(HERE, "explain.py"), structure_json, explanation,
           "--top", str(args.top)] + inline_arg
    label = "%d/%d explain" % (n, total)
    if not step(label, cmd, n=n, total=total, record=stages):
        return fail(label)

    analysis_arg = []
    if not args.skip_anchors:
        n += 1
        cmd = [sys.executable, os.path.join(HERE, "analyze.py"), clean, analysis,
               "--max-blocks", str(args.max_blocks)]
        if args.anchors:
            cmd += ["--anchors", os.path.abspath(args.anchors)]
        label = "%d/%d anchor scan" % (n, total)
        if not step(label, cmd, n=n, total=total, record=stages):
            return fail(label)
        analysis_arg = ["--analysis", analysis]

    n += 1
    cmd = [sys.executable, os.path.join(HERE, "report.py"), explanation, report_md,
           "--source", inp, "--clean", clean] + analysis_arg + meta_arg + inline_arg
    label = "%d/%d report" % (n, total)
    if not step(label, cmd, n=n, total=total, record=stages):
        return fail(label)

    # TOON is the token-efficient sibling of xray.json that an agent consumes
    # instead of the JSON when it wants the same data at a lower token cost.
    # This stage is unconditional: every run produces xray.toon, not just ones
    # invoked with an extra flag.
    n += 1
    cmd = [sys.executable, os.path.join(HERE, "toon_stats.py"), explanation, toon_path,
           "--stats", toon_stats]
    label = "%d/%d encode TOON" % (n, total)
    if not step(label, cmd, n=n, total=total, record=stages):
        return fail(label)

    write_pipeline_log(outdir, inp, stages)

    sys.stderr.write("[js-xray] done\n")
    print(explanation)
    return 0


if __name__ == "__main__":
    sys.exit(main())
