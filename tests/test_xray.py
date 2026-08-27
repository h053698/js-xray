#!/usr/bin/env python3
"""Test suite for js-xray. Run: python3 tests/test_xray.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skill", "scripts")
sys.path.insert(0, SCRIPTS)

import analyze  # noqa: E402
import explain  # noqa: E402
import node_env  # noqa: E402
import report  # noqa: E402
import structure  # noqa: E402
import xq  # noqa: E402

BT = chr(96)
PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print("  ok   %s" % name)
    else:
        FAIL.append((name, detail))
        print("  FAIL %s %s" % (name, detail))


def test_brace_matching():
    print("brace matching")
    # closing brace hidden inside a string must not end the block
    src = 'function f() { var s = "}"; return s; }'
    end = analyze.match_block(src, src.index("{"))
    check("string-embedded brace", end == len(src), "got %s want %s" % (end, len(src)))

    # brace inside a line comment
    src2 = "function g() {\n  // }\n  return 1;\n}"
    end2 = analyze.match_block(src2, src2.index("{"))
    check("comment brace", end2 == len(src2), "got %s" % end2)

    # brace inside a block comment
    src3 = "function h() {\n  /* } */\n  return 2;\n}"
    end3 = analyze.match_block(src3, src3.index("{"))
    check("block-comment brace", end3 == len(src3), "got %s" % end3)

    # template literal with nested interpolation containing braces
    src4 = "function t() { var x = " + BT + "a1b" + BT + "; return x; }"
    end4 = analyze.match_block(src4, src4.index("{"))
    check("template interpolation", end4 == len(src4), "got %s want %s" % (end4, len(src4)))

    # escaped quote inside a string
    src5 = 'function e() { var s = "a\\"}"; return s; }'
    end5 = analyze.match_block(src5, src5.index("{"))
    check("escaped quote", end5 == len(src5), "got %s want %s" % (end5, len(src5)))

    # nested blocks
    src6 = "function n() { if (a) { b(); } else { c(); } }"
    end6 = analyze.match_block(src6, src6.index("{"))
    check("nested blocks", end6 == len(src6), "got %s" % end6)

    # unterminated block returns None rather than raising
    check("unterminated", analyze.match_block("function u() { if (a) {", 13) is None)


def test_keyword_not_function():
    print("function detection")
    src = "for (var i = 0; i < n; i++) {\n  h ^= s.charCodeAt(i);\n}\n"
    nl = analyze.line_index(src)
    fn = analyze.enclosing_function(src, src.index("charCodeAt"), nl)
    check("for-loop is not a function", fn is None or fn["name"] not in analyze.NOT_FUNCTIONS,
          "got %s" % (fn or {}).get("name"))

    src2 = "async function realFn(a) {\n  return a.charCodeAt(0);\n}\n"
    nl2 = analyze.line_index(src2)
    fn2 = analyze.enclosing_function(src2, src2.index("charCodeAt"), nl2)
    check("named async function found", fn2 and fn2["name"] == "realFn", "got %s" % (fn2 or {}).get("name"))

    src3 = "const arrow = (a) => {\n  return a.charCodeAt(0);\n}\n"
    nl3 = analyze.line_index(src3)
    fn3 = analyze.enclosing_function(src3, src3.index("charCodeAt"), nl3)
    check("arrow function found", fn3 and fn3["name"] == "arrow", "got %s" % (fn3 or {}).get("name"))


def test_line_numbers():
    print("line numbers")
    src = "a\nb\nTARGET\nd\n"
    nl = analyze.line_index(src)
    check("offset->line", analyze.offset_to_line(nl, src.index("TARGET")) == 3,
          "got %s" % analyze.offset_to_line(nl, src.index("TARGET")))
    check("first line", analyze.offset_to_line(nl, 0) == 1)


def test_pipeline_end_to_end():
    print("end-to-end pipeline")
    fixture = os.path.join(ROOT, "fixtures", "sample_obfuscated.js")
    if not os.path.isfile(fixture):
        check("fixture present", False, fixture)
        return
    outdir = tempfile.mkdtemp(prefix="jsxray_test_")
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "xray.py"), fixture, "-o", outdir],
        capture_output=True, text=True)
    check("pipeline exit 0", proc.returncode == 0, proc.stderr[-400:])

    meta_path = os.path.join(outdir, "webcrack.json")
    if os.path.isfile(meta_path):
        meta = json.load(open(meta_path))
        check("webcrack deobfuscated", meta.get("deobfuscated") is True,
              "meta=%s" % meta.get("error", meta.get("string_array")))

    clean_path = os.path.join(outdir, "clean.js")
    if os.path.isfile(clean_path):
        clean = open(clean_path).read()
        # the whole point: encoded strings become readable identifiers
        check("string array inlined", "getEnforcementToken" in clean)
        check("endpoint recovered", "/backend-api/sentinel/req" in clean)
        check("no decoder calls left", "a0_0x1dce(" not in clean)

    ana_path = os.path.join(outdir, "analysis.json")
    if os.path.isfile(ana_path):
        ana = json.load(open(ana_path))
        names = [b["name"] for b in ana["key_blocks"]]
        check("key function extracted", "getEnforcementToken" in names, "got %s" % names)
        check("fnv anchor hit", "fnv_offset_basis" in ana["anchor_hits"])
        check("categories populated", len(ana["categories"]) >= 3, "got %s" % list(ana["categories"]))
        blocks = ana["key_blocks"]
        check("block has line range", blocks and blocks[0]["end_line"] >= blocks[0]["start_line"])

    rep_path = os.path.join(outdir, "report.md")
    if os.path.isfile(rep_path):
        rep = open(rep_path).read()
        check("report has porting guide", "Reimplementation notes" in rep)
        check("report has code fence", (BT * 3 + "python") in rep)
        check("report shows FNV hint", "16777619" in rep)

    pipeline_path = os.path.join(outdir, "pipeline.json")
    check("pipeline.json written", os.path.isfile(pipeline_path), pipeline_path)
    if os.path.isfile(pipeline_path):
        pipeline = json.load(open(pipeline_path))
        check("pipeline schema tagged", pipeline.get("schema") == "js-xray/pipeline/1",
              pipeline.get("schema"))
        check("pipeline records input path", pipeline.get("input") == fixture, pipeline.get("input"))
        stages = pipeline.get("stages", [])
        # full run (no --skip-* flags): all 8 stages present, in order, all ok
        check("pipeline has 8 stages", len(stages) == 8, [s.get("label") for s in stages])
        check("pipeline stages numbered in order",
              [s.get("n") for s in stages] == list(range(1, len(stages) + 1)),
              [s.get("n") for s in stages])
        check("pipeline stages all report total=8",
              all(s.get("total") == 8 for s in stages), [s.get("total") for s in stages])
        check("pipeline stages all ok", all(s.get("ok") is True for s in stages),
              [(s.get("label"), s.get("ok")) for s in stages])
        for s in stages:
            check("stage %r has label/ok/cmd/meta fields" % s.get("label"),
                  all(k in s for k in ("label", "ok", "cmd", "meta", "n", "total", "duration_s")),
                  s)
        labels = [s.get("label", "") for s in stages]
        check("stage order matches pipeline description",
              ["deobfuscate" in labels[0], "inline" in labels[1], "deflatten" in labels[2],
               "structure" in labels[3], "explain" in labels[4], "anchor" in labels[5],
               "report" in labels[6], "TOON" in labels[7]] == [True] * 8,
              labels)
        # JSON-emitting stages (webcrack, inline, deflatten, anchors) parse into dicts
        check("webcrack stage meta parsed as dict", isinstance(stages[0].get("meta"), dict), stages[0].get("meta"))
        check("inline stage meta parsed as dict", isinstance(stages[1].get("meta"), dict), stages[1].get("meta"))
        check("deflatten stage meta parsed as dict", isinstance(stages[2].get("meta"), dict), stages[2].get("meta"))
        check("anchor stage meta parsed as dict", isinstance(stages[5].get("meta"), dict), stages[5].get("meta"))
        # summary-only stages (structure, explain, report) keep the raw stdout string
        check("structure stage meta is a raw string", isinstance(stages[3].get("meta"), str), stages[3].get("meta"))
        check("explain stage meta is a raw string", isinstance(stages[4].get("meta"), str), stages[4].get("meta"))


def test_deobfuscation_reports_both_passes():
    """Neither inlining pass may be published as if it were the whole story.

    sample_obfuscated.js is the exact shape that misled a reader: webcrack
    resolves the module-level string array in the first pass, and inline_strings
    finds no per-scope arrays left, so the second pass legitimately reports 0.
    Published as a bare "strings_inlined: 0" that read as "nothing was decoded",
    and the reader went to webcrack.json to discover 26 strings had been inlined
    after all. Both numbers have to be visible, each labelled with the pass it
    came from.
    """
    print("deobfuscation reports both passes")
    fixture = os.path.join(ROOT, "fixtures", "sample_obfuscated.js")
    if not os.path.isfile(fixture):
        check("fixture present for two-pass reporting", False, fixture)
        return
    outdir = tempfile.mkdtemp(prefix="jsxray_deob_")
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "xray.py"), fixture, "-o", outdir],
            capture_output=True, text=True)
        check("two-pass run exits 0", proc.returncode == 0, proc.stderr[-300:])

        wc = json.load(open(os.path.join(outdir, "webcrack.json")))
        inline = json.load(open(os.path.join(outdir, "inline.json")))
        wc_inlined = (wc.get("changes") or {}).get("inline-decoded-strings", 0)
        second = inline.get("replaced", 0)
        # the premise of this test: the fixture really does split this way
        check("fixture exercises the misleading case: webcrack > 0, second pass 0",
              wc_inlined > 0 and second == 0, (wc_inlined, second))

        data = json.load(open(os.path.join(outdir, "xray.json")))
        deob = data.get("deobfuscation") or {}
        check("deobfuscation block present", bool(deob), deob)
        by_pass = {p.get("pass"): p for p in deob.get("passes") or []}
        check("both passes are reported separately",
              set(by_pass) == {"webcrack", "inline_strings"}, list(by_pass))
        check("the webcrack pass carries webcrack's own count",
              by_pass.get("webcrack", {}).get("strings_inlined") == wc_inlined,
              (by_pass.get("webcrack"), wc_inlined))
        check("the second pass carries its own count",
              by_pass.get("inline_strings", {}).get("strings_inlined") == second,
              (by_pass.get("inline_strings"), second))
        check("the total is the sum of the passes",
              deob.get("strings_inlined_total") == wc_inlined + second,
              (deob.get("strings_inlined_total"), wc_inlined, second))
        # the regression proper: no unqualified field may still say 0 here
        check("no bare strings_inlined survives at the block root",
              "strings_inlined" not in deob, list(deob))

        # ...and a reader who only skims the caveats is told the same thing
        notes = " ".join(data.get("confidence_notes") or [])
        check("a caveat explains the zero pass",
              "two passes" in notes and "does not mean nothing was decoded" in notes,
              notes[-300:])

        # both human-facing views agree with the file
        rep = open(os.path.join(outdir, "report.md")).read()
        check("report.md shows the total and both passes",
              ("%s total" % (wc_inlined + second)) in rep
              and "webcrack %d" % wc_inlined in rep
              and "inline_strings %d" % second in rep,
              [l for l in rep.splitlines() if "strings inlined" in l])

        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "xq.py"), outdir, "summary"],
            capture_output=True, text=True)
        check("xq summary shows the total, not one pass's figure",
              "%d strings inlined in total" % (wc_inlined + second) in proc.stdout,
              proc.stdout[-300:])
        check("xq summary names each pass",
              "webcrack" in proc.stdout and "inline_strings" in proc.stdout,
              proc.stdout[-300:])
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_truncated_functions_are_visible():
    """functions[] is an excerpt, and the artifact has to say so.

    The default --top 25 is kept deliberately -- detailing every function of a
    291-function file roughly triples xray.json, which defeats the point of an
    artifact an agent reads instead of the source. What was wrong was not the
    number but that nothing marked it as a cut: a reader took functions[] for the
    whole file and read clean.js by hand rather than raising --top or asking xq.
    """
    print("truncation is visible in the outputs")
    struct = os.path.join(ROOT, "tests", "samples", "xray_sentinel_sdk", "structure.json")
    if not os.path.isfile(struct):
        check("structure.json present for truncation test", False, struct)
        return
    total = len(json.load(open(struct)).get("functions") or [])
    check("the sample has more functions than --top", total > 25, total)

    tmp = tempfile.mkdtemp(prefix="jsxray_top_")
    try:
        out = os.path.join(tmp, "xray.json")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "explain.py"), struct, out, "--top", "5"],
            capture_output=True, text=True)
        check("explain exits 0 when truncating", proc.returncode == 0, proc.stderr[-300:])
        # the run's own log line says it, while raising --top is still cheap
        check("the stage log states the truncation",
              "5 detailed" in proc.stdout and "omitted" in proc.stdout, proc.stdout)

        data = json.load(open(out))
        s = data["summary"]
        check("summary.functions stays the whole count", s["functions"] == total,
              (s["functions"], total))
        check("summary says how many are detailed", s["functions_detailed"] == 5,
              s.get("functions_detailed"))
        check("summary says how many were left out",
              s["functions_omitted"] == total - 5, s.get("functions_omitted"))
        check("functions[] really holds only that many", len(data["functions"]) == 5,
              len(data["functions"]))
        notes = " ".join(data.get("confidence_notes") or [])
        check("a caveat points at structure.json and xq for the rest",
              "structure.json" in notes and "xq find" in notes
              and ("%d functions" % total) in notes, notes[-320:])

        # and when nothing was cut, the fields are still there and say zero, so
        # the reader never has to guess whether a missing field means "not cut"
        full = os.path.join(tmp, "full.json")
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "explain.py"), struct,
                        full, "--top", str(total)], capture_output=True, text=True)
        fs = json.load(open(full))["summary"]
        check("an untruncated run reports zero omitted",
              fs["functions_omitted"] == 0 and fs["functions_detailed"] == total,
              (fs.get("functions_omitted"), fs.get("functions_detailed")))
        fnotes = " ".join(json.load(open(full)).get("confidence_notes") or [])
        check("an untruncated run does not claim a truncation",
              "not detailed here" not in fnotes, fnotes[-200:])

        # xq surfaces it next to the count it qualifies
        run = os.path.join(tmp, "run.xrayjs")
        os.makedirs(run)
        shutil.copy(out, os.path.join(run, "xray.json"))
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "xq.py"), run, "summary"],
            capture_output=True, text=True)
        check("xq summary states the truncation under the function count",
              "details 5 of %d" % total in proc.stdout and "xq show" in proc.stdout,
              proc.stdout[:400])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_default_outdir_naming():
    """Default output dir must be <stem>.xrayjs/ next to the input, and an
    explicit -o override must still be honoured verbatim (DEC-003 / REQ-001)."""
    print("default outdir naming")
    workdir = tempfile.mkdtemp(prefix="jsxray_outdir_")
    try:
        js = os.path.join(workdir, "sentinel_pow.js")
        open(js, "w").write("export const sum = (a, b) => a + b;\n")

        # default: no -o given -> "<stem>.xrayjs" next to the input, not "xray_<stem>"
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "xray.py"), js,
             "--skip-deobfuscate", "--skip-inline", "--skip-anchors"],
            capture_output=True, text=True)
        check("default naming: exit 0", proc.returncode == 0, proc.stderr[-400:])
        expected_default = os.path.join(workdir, "sentinel_pow.xrayjs")
        legacy_default = os.path.join(workdir, "xray_sentinel_pow")
        check("default naming: <stem>.xrayjs created", os.path.isdir(expected_default), expected_default)
        check("default naming: report.md present", os.path.isfile(os.path.join(expected_default, "report.md")))
        check("default naming: legacy xray_<stem> not created", not os.path.isdir(legacy_default), legacy_default)

        # explicit -o must still be honoured exactly, unaffected by the default rule
        custom_outdir = os.path.join(workdir, "wherever-i-want")
        proc2 = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "xray.py"), js, "-o", custom_outdir,
             "--skip-deobfuscate", "--skip-inline", "--skip-anchors"],
            capture_output=True, text=True)
        check("outdir override: exit 0", proc2.returncode == 0, proc2.stderr[-400:])
        check("outdir override: exact path used", os.path.isdir(custom_outdir), custom_outdir)
        check("outdir override: report.md present", os.path.isfile(os.path.join(custom_outdir, "report.md")))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_custom_anchors():
    print("custom anchors")
    outdir = tempfile.mkdtemp(prefix="jsxray_anchor_")
    js = os.path.join(outdir, "in.js")
    open(js, "w").write("function findMe() { var magic = 'ZZTOP_MARKER'; return magic; }\n")
    anchors = os.path.join(outdir, "anchors.json")
    json.dump([{"label": "zztop", "pattern": "ZZTOP_MARKER", "regex": False}], open(anchors, "w"))
    ana = os.path.join(outdir, "a.json")
    proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "analyze.py"), js, ana, "--anchors", anchors],
                          capture_output=True, text=True)
    check("custom anchor run", proc.returncode == 0, proc.stderr[-300:])
    if os.path.isfile(ana):
        data = json.load(open(ana))
        check("custom anchor hit", "zztop" in data["anchor_hits"])
        check("custom anchor block", [b["name"] for b in data["key_blocks"]] == ["findMe"],
              "got %s" % [b["name"] for b in data["key_blocks"]])


def test_graceful_on_plain_file():
    print("plain file handling")
    outdir = tempfile.mkdtemp(prefix="jsxray_plain_")
    js = os.path.join(outdir, "plain.js")
    open(js, "w").write("export const sum = (a, b) => a + b;\n")
    proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "xray.py"), js, "-o", outdir],
                          capture_output=True, text=True)
    check("plain file exit 0", proc.returncode == 0, proc.stderr[-300:])
    check("report written", os.path.isfile(os.path.join(outdir, "report.md")))


def test_scoped_string_arrays():
    """The second pass must resolve per-scope arrays without cross-contamination."""
    print("scoped string arrays")
    fixture = os.path.join(ROOT, "fixtures", "multi_scope_arrays.js")
    if not os.path.isfile(fixture):
        check("multi-scope fixture present", False, fixture)
        return

    outdir = tempfile.mkdtemp(prefix="jsxray_scope_")
    out = os.path.join(outdir, "out.js")
    meta_path = os.path.join(outdir, "meta.json")
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "inline_strings.py"), fixture, out, "--meta", meta_path],
        capture_output=True, text=True)
    check("inline exit 0", proc.returncode == 0, proc.stderr[-400:])
    if not os.path.isfile(meta_path):
        check("inline meta written", False)
        return

    meta = json.load(open(meta_path))
    if not meta.get("ok"):
        # no compatible Node: the pass degrades instead of corrupting the file
        check("degrades without node", open(out).read() == open(fixture).read(),
              meta.get("error", "?"))
        return

    code = open(out).read()
    check("output still parses", meta.get("valid") is True, meta.get("parse_error"))
    check("not rolled back", meta.get("rolled_back") is False)

    # scope A and scope B both alias `i`, to different arrays
    check("scope A alias resolved", "s.substring(0, 2)" in code)
    check("scope B alias resolved", 'fetch("https://example.invalid/api")' in code)
    # Cross-scope contamination check. Both scopes alias `i`, so a textual pass
    # resolves one of them against the wrong array. Assert on the resolved call
    # sites directly -- a text window would also span the array declarations.
    def strip_comments(text):
        # fixture comments name the expected values, so compare code only
        return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("//"))

    body_a = strip_comments(code.split("globalThis.scopeA", 1)[1].split("})();", 1)[0])
    body_b = strip_comments(code.split("globalThis.scopeB", 1)[1].split("})();", 1)[0])
    check("scope A kept its own array", "example.invalid" not in body_a, body_a.strip())
    check("scope B kept its own array", "alpha" not in body_b, body_b.strip())

    # offset form  arr[idx -= 5]
    check("offset decoder resolved", "s.charCodeAt(0)" in code)

    # computed class keys must become valid syntax, not `async .run()`
    check("class method key", "initialize()" in code)
    check("async class method key", "async run()" in code)
    code_lines = [ln for ln in code.splitlines() if not ln.strip().startswith("//")]
    check("no async-dot syntax error", not any("async ." in ln for ln in code_lines))
    check("static class method key", "static teardown()" in code)

    # a decoder wrapping atob does more than an index lookup; leave it alone
    check("impure decoder untouched", "DEC_E(0)" in code)

    check("no decoder calls left", "DEC_A(" not in code.split("globalThis.scopeA", 1)[-1])


def test_inline_syntax_gate():
    """A rewrite that would not parse must roll back to the input."""
    print("inline syntax gate")
    outdir = tempfile.mkdtemp(prefix="jsxray_gate_")
    js = os.path.join(outdir, "broken.js")
    # deliberately unparseable input: the transform must fail closed
    open(js, "w").write("function ( { this is not javascript\n")
    out = os.path.join(outdir, "out.js")
    meta_path = os.path.join(outdir, "meta.json")
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "inline_strings.py"), js, out, "--meta", meta_path],
        capture_output=True, text=True)
    check("gate exit 0", proc.returncode == 0, proc.stderr[-300:])
    check("input preserved", os.path.isfile(out) and open(out).read() == open(js).read())


def _run_node(node, path):
    """Execute a fixture and return its stdout, or None if it did not run."""
    proc = subprocess.run([node, path], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return None, proc.stderr[-300:]
    return proc.stdout, ""


def test_deflatten_execution_equivalence():
    """The check that actually protects this pass: run it, do not just parse it.

    A deflattening bug does not produce broken syntax. Drop the live branch
    instead of the dead one, or reorder case bodies that were not independent,
    and the result is still valid JavaScript -- `node --check` passes, every
    later stage passes, and the analysis then describes code that never ran.
    So the fixture is built to make its behaviour observable (every effect is
    appended to TRACE and printed at the end) and this test runs the file before
    and after the transform and compares stdout byte for byte. That comparison,
    not the syntax gate, is what makes the stage trustworthy (ACT-008).
    """
    print("deflatten execution equivalence")
    node, _ver = node_env.resolve()
    if not node:
        check("node available for deflatten test", False, "no node found")
        return

    fixture = os.path.join(ROOT, "fixtures", "flattened.js")
    if not os.path.isfile(fixture):
        check("flattened fixture present", False, fixture)
        return

    outdir = tempfile.mkdtemp(prefix="jsxray_deflat_")
    try:
        out = os.path.join(outdir, "out.js")
        meta_path = os.path.join(outdir, "meta.json")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "deflatten.py"), fixture, out,
             "--meta", meta_path],
            capture_output=True, text=True)
        check("deflatten exit 0", proc.returncode == 0, proc.stderr[-400:])
        if not os.path.isfile(meta_path):
            check("deflatten meta written", False)
            return

        meta = json.load(open(meta_path))
        if not meta.get("ok"):
            # no compatible Node: the pass degrades instead of corrupting the file
            check("degrades without node", open(out).read() == open(fixture).read(),
                  meta.get("error", "?"))
            return

        check("deflatten not rolled back", meta.get("rolled_back") is False, meta.get("error"))

        # the equivalence assertion itself
        before, before_err = _run_node(node, fixture)
        after, after_err = _run_node(node, out)
        check("fixture runs before transform", before is not None, before_err)
        check("fixture runs after transform", after is not None, after_err)
        check("stdout identical before/after", before is not None and before == after,
              "before=%r after=%r" % (before, after))
        # a fixture that printed nothing would make the check above vacuous
        check("fixture output is non-trivial", bool(before and before.strip()), repr(before))

        # both patterns must actually have fired, or the test proves nothing
        check("dead branches dropped", meta.get("dead_branches_dropped", 0) >= 3,
              meta.get("dead_branches_dropped"))
        check("switch sequences linearised", meta.get("switch_sequences_linearised", 0) >= 2,
              meta.get("switch_sequences_linearised"))
        check("nothing was refused in the clean fixture",
              not meta.get("switch_skips") and not meta.get("dead_branch_skips"),
              "%s %s" % (meta.get("switch_skips"), meta.get("dead_branch_skips")))

        code = open(out).read()
        # the flattening machinery itself must be gone
        check("dispatcher switch removed", "switch (" not in code, code[:200])
        check("sequence split removed", 'split("|")' not in code)
        check("dead branch text removed", "unreachable-inner" not in code)

        # ACT-008: a real reduction, not a rearrangement
        before_lines = len(open(fixture).read().splitlines())
        after_lines = len(code.splitlines())
        check("line count meaningfully reduced", after_lines <= before_lines * 0.8,
              "%d -> %d" % (before_lines, after_lines))
        check("meta reports the reduction",
              meta.get("lines_after", 0) < meta.get("lines_before", 0),
              "%s -> %s" % (meta.get("lines_before"), meta.get("lines_after")))
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_deflatten_leaves_undecidable_alone():
    """Constructs the pass cannot prove safe must survive verbatim.

    This is the test that guards against the failure mode that matters: a
    too-eager rewrite here is invisible downstream, because the output is still
    valid JavaScript. Each construct in the fixture looks like a handled pattern
    but carries something that makes the rewrite unsound -- a runtime-computed
    sequence, a break out of the dispatcher, an observed cursor, a mutated
    storage object, same-named variables from different scopes, an impure
    comparison helper, a var hoisted out of the dead branch. All of them must be
    left exactly as they are, and the refusal must be recorded rather than
    silent.
    """
    print("deflatten conservatism")
    node, _ver = node_env.resolve()
    fixture = os.path.join(ROOT, "fixtures", "flattened_ambiguous.js")
    if not os.path.isfile(fixture):
        check("ambiguous fixture present", False, fixture)
        return

    outdir = tempfile.mkdtemp(prefix="jsxray_deflat_amb_")
    try:
        out = os.path.join(outdir, "out.js")
        meta_path = os.path.join(outdir, "meta.json")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "deflatten.py"), fixture, out,
             "--meta", meta_path],
            capture_output=True, text=True)
        check("deflatten exit 0 on ambiguous input", proc.returncode == 0, proc.stderr[-400:])
        if not os.path.isfile(meta_path):
            check("ambiguous meta written", False)
            return
        meta = json.load(open(meta_path))
        if not meta.get("ok"):
            check("degrades without node", open(out).read() == open(fixture).read(),
                  meta.get("error", "?"))
            return

        original = open(fixture).read()
        code = open(out).read()

        check("nothing was transformed", meta.get("dead_branches_dropped") == 0 and
              meta.get("switch_sequences_linearised") == 0,
              "dropped=%s linearised=%s" % (meta.get("dead_branches_dropped"),
                                            meta.get("switch_sequences_linearised")))
        # byte-identical, not merely equivalent: nothing was rewritten at all
        check("output byte-identical to input", code == original)

        # each guarded construct is still there
        for marker in ("KEEP_RUNTIME_SEQ", "KEEP_EARLY_BREAK", "KEEP_OBSERVED_CURSOR",
                       "KEEP_MUTATED_STORE", "KEEP_SHADOWED", "KEEP_IMPURE_HELPER",
                       "KEEP_HOISTED_VAR"):
            check("kept %s" % marker, marker in code)

        # the pass must have looked at them and said no, not failed to find them
        check("dispatchers were examined", meta.get("switch_sequences_examined", 0) >= 4,
              meta.get("switch_sequences_examined"))
        check("refusals recorded with reasons", bool(meta.get("switch_skips")),
              meta.get("switch_skips"))
        check("dead-branch refusal recorded", bool(meta.get("dead_branch_skips")),
              meta.get("dead_branch_skips"))
        reasons = " ".join(meta.get("switch_skips", {}).keys())
        check("runtime sequence refused by name", "not statically known" in reasons, reasons)
        check("dispatcher break refused by name", "break would exit" in reasons, reasons)
        check("observed cursor refused by name", "read elsewhere" in reasons, reasons)

        if node:
            before, before_err = _run_node(node, fixture)
            after, after_err = _run_node(node, out)
            check("ambiguous fixture runs", before is not None, before_err)
            check("ambiguous stdout identical", before is not None and before == after,
                  "before=%r after=%r" % (before, after))
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_deflatten_rollback():
    """An output that would not parse must roll back, recording that it did.

    Same fail-closed contract as the inlining pass: downstream stages get the
    input unchanged rather than a broken file, and `rolled_back` says so instead
    of the run looking clean.
    """
    print("deflatten rollback")
    outdir = tempfile.mkdtemp(prefix="jsxray_deflat_gate_")
    try:
        js = os.path.join(outdir, "broken.js")
        open(js, "w").write("function ( { this is not javascript\n")
        out = os.path.join(outdir, "out.js")
        meta_path = os.path.join(outdir, "meta.json")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "deflatten.py"), js, out,
             "--meta", meta_path],
            capture_output=True, text=True)
        check("rollback exit 0", proc.returncode == 0, proc.stderr[-300:])
        check("input preserved on failure",
              os.path.isfile(out) and open(out).read() == open(js).read())
        if os.path.isfile(meta_path):
            meta = json.load(open(meta_path))
            check("failure is visible in meta",
                  meta.get("ok") is False or meta.get("rolled_back") is True, meta)

        # An output the transform itself produced but node rejects: force it by
        # pointing the wrapper at a syntactically fine input and then checking
        # that a rejected output rolls back. Simulated by handing the wrapper an
        # input whose own syntax node accepts but babel-generated output would
        # not exist for -- instead assert the gate is wired at all.
        node, _ver = node_env.resolve()
        if node:
            good = os.path.join(outdir, "good.js")
            open(good, "w").write("var a = 1;\nconsole.log(a);\n")
            out2 = os.path.join(outdir, "out2.js")
            meta2 = os.path.join(outdir, "meta2.json")
            subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "deflatten.py"), good, out2,
                 "--meta", meta2], capture_output=True, text=True)
            if os.path.isfile(meta2):
                m2 = json.load(open(meta2))
                check("node --check gate ran", m2.get("node_check") == "ok", m2.get("node_check"))
                check("no-op input stays ok", m2.get("ok") is True, m2)
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_deflatten_stage_in_pipeline():
    """The pipeline must run deflatten between inline and structure, and clean.js
    must be the deflattened file -- not the inlined one.
    """
    print("deflatten pipeline stage")
    fixture = os.path.join(ROOT, "fixtures", "flattened.js")
    if not os.path.isfile(fixture):
        check("flattened fixture present for pipeline", False, fixture)
        return

    outdir = tempfile.mkdtemp(prefix="jsxray_deflat_pipe_")
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "xray.py"), fixture, "-o", outdir],
            capture_output=True, text=True)
        check("pipeline exit 0 with deflatten", proc.returncode == 0, proc.stderr[-400:])

        meta_path = os.path.join(outdir, "deflatten.json")
        check("deflatten.json written", os.path.isfile(meta_path), meta_path)
        check("inline.js kept as the intermediate",
              os.path.isfile(os.path.join(outdir, "inline.js")))

        pipeline_path = os.path.join(outdir, "pipeline.json")
        if os.path.isfile(pipeline_path):
            stages = json.load(open(pipeline_path)).get("stages", [])
            labels = [s.get("label", "") for s in stages]
            check("eight stages recorded", len(stages) == 8, labels)
            names = [lbl.split(" ", 1)[-1] for lbl in labels]
            check("deflatten sits between inline and structure",
                  len(names) >= 4 and "inline" in names[1] and "deflatten" in names[2]
                  and "structure" in names[3], names)
            check("every stage numbered out of 8",
                  all(s.get("total") == 8 for s in stages),
                  [(s.get("n"), s.get("total")) for s in stages])
            deflat = next((s for s in stages if "deflatten" in s.get("label", "")), None)
            check("deflatten stage ok", deflat is not None and deflat.get("ok") is True, deflat)

        clean_path = os.path.join(outdir, "clean.js")
        if os.path.isfile(clean_path):
            clean = open(clean_path).read()
            inlined = open(os.path.join(outdir, "inline.js")).read()
            meta = json.load(open(meta_path)) if os.path.isfile(meta_path) else {}
            if meta.get("ok") and meta.get("switch_sequences_linearised", 0):
                check("clean.js is the deflattened output", clean != inlined)
                check("clean.js has no dispatcher left", "switch (" not in clean)
                check("clean.js is shorter than the inlined file",
                      len(clean.splitlines()) < len(inlined.splitlines()),
                      "%d vs %d" % (len(clean.splitlines()), len(inlined.splitlines())))
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def _classification_rate(js_path):
    """Run structure + explain on one file and return (functions, unclassified).

    Deliberately measured rather than asserted from the transform's own counters:
    the point of wrapper inlining is what the classifier can see afterwards, and a
    wrappers_inlined count proves only that the rewrite happened, not that it
    helped. Returns (0, 0) when the stages cannot run.
    """
    tmp = tempfile.mkdtemp(prefix="jsxray_rate_")
    try:
        st = os.path.join(tmp, "structure.json")
        ex = os.path.join(tmp, "explain.json")
        p1 = subprocess.run([sys.executable, os.path.join(SCRIPTS, "structure.py"), js_path, st],
                            capture_output=True, text=True)
        if p1.returncode != 0 or not os.path.isfile(st):
            return 0, 0
        p2 = subprocess.run([sys.executable, os.path.join(SCRIPTS, "explain.py"), st, ex],
                            capture_output=True, text=True)
        if p2.returncode != 0 or not os.path.isfile(ex):
            return 0, 0
        data = json.load(open(ex))
        fns = data.get("functions") or []
        unclassified = 0
        for fn in fns:
            roles = [r["role"] if isinstance(r, dict) else r for r in (fn.get("roles") or [])]
            if not roles or roles == ["unclassified"]:
                unclassified += 1
        return len(fns), unclassified
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_wrapper_inlining_execution_equivalence():
    """Pure call forwarders are resolved, and the rewrite is verified by running it.

    `S.DmnGW(fetch, url, opts)` where DmnGW is `function (a, b, c) { return a(b, c); }`
    means `fetch(url, opts)`. The wrapper is behaviour-preserving, so the only way
    to tell a correct rewrite from a wrong one is to execute both: swapping two
    arguments or dropping a `this` binding still parses and still passes every
    later stage. The fixture routes every effect through TRACE, so this test
    compares stdout byte for byte before and after (ACT-010).
    """
    print("wrapper inlining execution equivalence")
    node, _ver = node_env.resolve()
    if not node:
        check("node available for wrapper test", False, "no node found")
        return

    fixture = os.path.join(ROOT, "fixtures", "wrapped_calls.js")
    if not os.path.isfile(fixture):
        check("wrapped_calls fixture present", False, fixture)
        return

    outdir = tempfile.mkdtemp(prefix="jsxray_wrap_")
    try:
        out = os.path.join(outdir, "out.js")
        meta_path = os.path.join(outdir, "meta.json")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "deflatten.py"), fixture, out,
             "--meta", meta_path],
            capture_output=True, text=True)
        check("wrapper deflatten exit 0", proc.returncode == 0, proc.stderr[-400:])
        if not os.path.isfile(meta_path):
            check("wrapper meta written", False)
            return
        meta = json.load(open(meta_path))
        if not meta.get("ok"):
            check("degrades without node", open(out).read() == open(fixture).read(),
                  meta.get("error", "?"))
            return
        check("wrapper pass not rolled back", meta.get("rolled_back") is False, meta.get("error"))

        before, before_err = _run_node(node, fixture)
        after, after_err = _run_node(node, out)
        check("wrapper fixture runs before", before is not None, before_err)
        check("wrapper fixture runs after", after is not None, after_err)
        check("wrapper stdout identical before/after", before is not None and before == after,
              "before=%r after=%r" % (before, after))
        check("wrapper fixture output non-trivial", bool(before and before.strip()), repr(before))

        check("wrappers were inlined", meta.get("wrappers_inlined", 0) >= 5,
              meta.get("wrappers_inlined"))
        check("meta counts wrappers examined", meta.get("wrappers_examined", 0) >= 10,
              meta.get("wrappers_examined"))

        code = open(out).read()
        # the calls the role classifier matches on must now be written literally
        for call in ("fetch(url,", "JSON.stringify(payload)", "JSON.parse(rawA)",
                     "Date.now()", 'atob("cGF5bG9hZA==")'):
            check("call surfaced: %s" % call, call in code.replace(", ", ","), None)
        # and the forwarding call sites are gone. Matched with the STORE. prefix
        # because the fixture's own header comment documents the pattern using a
        # differently-named object, and that comment is preserved by design.
        check("DmnGW forwarder call site gone", "STORE.DmnGW(" not in code)
        check("kQrTz forwarder call site gone", "STORE.kQrTz(" not in code)
        check("nUlla forwarder call site gone", "STORE.nUlla(" not in code)
        check("xxKwe forwarder call site gone", "STORE.xxKwe(" not in code)
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_wrapper_inlining_refuses_lookalikes():
    """Wrappers that only look like forwarders must survive byte-identical.

    This is the half of the fixture that matters most. A wrong rewrite here is
    strictly worse than no rewrite: the output still parses, nothing downstream
    can detect it, and explain would then report a call that never happened --
    a manufactured finding rather than a missing one (RSK-006). Each construct
    carries one disqualifying property, and the refusal must be recorded with a
    reason rather than being a silent non-match.
    """
    print("wrapper inlining conservatism")
    node, _ver = node_env.resolve()
    fixture = os.path.join(ROOT, "fixtures", "wrapped_calls.js")
    if not os.path.isfile(fixture):
        check("wrapped_calls fixture present for refusal test", False, fixture)
        return

    outdir = tempfile.mkdtemp(prefix="jsxray_wrap_neg_")
    try:
        out = os.path.join(outdir, "out.js")
        meta_path = os.path.join(outdir, "meta.json")
        subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "deflatten.py"), fixture, out,
             "--meta", meta_path],
            capture_output=True, text=True)
        if not os.path.isfile(meta_path):
            check("wrapper refusal meta written", False)
            return
        meta = json.load(open(meta_path))
        if not meta.get("ok"):
            check("degrades without node", open(out).read() == open(fixture).read(),
                  meta.get("error", "?"))
            return

        code = open(out).read()
        # every unsound shape is still exactly as it was written
        for marker in ("KEEP_SWAPPED_ARGS", "KEEP_THIS_BINDING", "KEEP_SIDE_EFFECT",
                       "KEEP_REASSIGNED_PROP", "KEEP_ARITY_MISMATCH",
                       "KEEP_MEMBER_CALLEE", "KEEP_EXTRA_ARG",
                       "KEEP_ESCAPING_STORE", "KEEP_SHADOWED_NAMESPACE"):
            check("kept %s" % marker, marker in code)

        # the wrapper bodies themselves must not have been rewritten
        check("swapped wrapper body intact", "return a(c, b)" in code)
        check("this-bound wrapper body intact", "return a.call(b, c)" in code)
        check("extra-argument wrapper body intact", 'return a(b, "injected")' in code)

        # refusals are recorded with reasons, not silent
        skips = meta.get("wrapper_skips") or {}
        check("wrapper refusals recorded", bool(skips), skips)
        reasons = " ".join(skips.keys())
        check("argument reordering refused by name",
              "reorders, drops or transforms" in reasons, reasons)
        check("this binding refused by name", "this binding" in reasons, reasons)
        check("arity mismatch refused by name", "arity" in reasons, reasons)
        check("shadowed namespace refused by name", "shadowed" in reasons, reasons)

        # the side-effecting wrapper is refused because its body is not a bare
        # return, so it is not forwarder-shaped and is never counted -- what
        # matters is that its call site is untouched
        check("side-effect wrapper call site intact", "STORE.logged(atob" in code)
        # and the reassigned / escaping storage objects are refused by the shared
        # closed-object judgement, before the wrapper rules are even reached
        check("reassigned wrapper call site intact", "STORE.pick(wrap" in code)
        check("escaping-store call site intact", "STORE.via(wrap" in code)

        if node:
            before, before_err = _run_node(node, fixture)
            after, after_err = _run_node(node, out)
            check("wrapper fixture still runs", before is not None, before_err)
            check("wrapper refusal stdout identical", before is not None and before == after,
                  "before=%r after=%r" % (before, after))
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_wrapper_inlining_improves_classification():
    """The measured point of the pass: explain must see the real calls (ACT-010).

    Wrapper inlining is not a readability change, it is what makes the role
    classifier work at all -- it matches call text against markers like fetch and
    JSON.stringify, so a call behind a forwarder is a function that reports
    "(unclassified)". This test measures the unclassified rate before and after
    the transform instead of asserting an improvement, so a regression to no
    improvement shows up as a number rather than a passing test.
    """
    print("wrapper inlining classification gain")
    node, _ver = node_env.resolve()
    if not node:
        check("node available for classification test", False, "no node found")
        return
    fixture = os.path.join(ROOT, "fixtures", "wrapped_calls.js")
    if not os.path.isfile(fixture):
        check("wrapped_calls fixture present for classification", False, fixture)
        return

    outdir = tempfile.mkdtemp(prefix="jsxray_wrap_cls_")
    try:
        out = os.path.join(outdir, "out.js")
        meta_path = os.path.join(outdir, "meta.json")
        subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "deflatten.py"), fixture, out,
             "--meta", meta_path],
            capture_output=True, text=True)
        if not os.path.isfile(meta_path) or not json.load(open(meta_path)).get("ok"):
            check("classification measurable", False, "deflatten did not run")
            return

        total_before, unc_before = _classification_rate(fixture)
        total_after, unc_after = _classification_rate(out)
        if not total_before or not total_after:
            check("explain ran on both files", False,
                  "before=%s after=%s" % (total_before, total_after))
            return

        pct_before = 100.0 * unc_before / total_before
        pct_after = 100.0 * unc_after / total_after
        print("    unclassified: %d/%d (%.1f%%) -> %d/%d (%.1f%%)" % (
            unc_before, total_before, pct_before, unc_after, total_after, pct_after))
        check("unclassified rate did not get worse", pct_after <= pct_before,
              "%.1f%% -> %.1f%%" % (pct_before, pct_after))
        check("unclassified rate improved", unc_after < unc_before,
              "%d -> %d of %d" % (unc_before, unc_after, total_before))

        # and the improvement is the specific one claimed: a role that exists only
        # because a marker call became visible
        tmp = tempfile.mkdtemp(prefix="jsxray_wrap_roles_")
        try:
            st = os.path.join(tmp, "s.json")
            ex = os.path.join(tmp, "e.json")
            subprocess.run([sys.executable, os.path.join(SCRIPTS, "structure.py"), out, st],
                           capture_output=True, text=True)
            subprocess.run([sys.executable, os.path.join(SCRIPTS, "explain.py"), st, ex],
                           capture_output=True, text=True)
            if os.path.isfile(ex):
                data = json.load(open(ex))
                by_name = {}
                for fn in data.get("functions") or []:
                    roles = [r["role"] if isinstance(r, dict) else r
                             for r in (fn.get("roles") or [])]
                    by_name[fn.get("name") or fn.get("display") or ""] = roles
                beacon = by_name.get("sendBeacon", [])
                check("hidden fetch produces a network role",
                      any("network" in r for r in beacon), beacon)
                parse_all = by_name.get("parseAll", [])
                check("hidden JSON.parse produces a serialization role",
                      any("serial" in r for r in parse_all), parse_all)
                # the calls themselves are in the structural facts explain reads
                sdata = json.load(open(st))
                calls = {}
                for fn in sdata.get("functions") or []:
                    calls[fn.get("name") or ""] = fn.get("calls") or []
                check("fetch appears in sendBeacon's calls",
                      "fetch" in calls.get("sendBeacon", []), calls.get("sendBeacon"))
                check("JSON.stringify appears in sendBeacon's calls",
                      "JSON.stringify" in calls.get("sendBeacon", []),
                      calls.get("sendBeacon"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_deflatten_regression_on_existing_fixtures():
    """Deflatten must not disturb the files the rest of the suite depends on.

    None of them carries the flattening residue this pass targets, so the
    correct outcome is that every one passes through byte-identical -- and,
    where node is available, still produces the same output.
    """
    print("deflatten leaves existing fixtures alone")
    targets = [
        os.path.join(ROOT, "fixtures", "sample_obfuscated.js"),
        os.path.join(ROOT, "fixtures", "multi_scope_arrays.js"),
        os.path.join(ROOT, "tests", "samples", "sentinel_sdk.js"),
    ]
    outdir = tempfile.mkdtemp(prefix="jsxray_deflat_reg_")
    try:
        for target in targets:
            name = os.path.basename(target)
            if not os.path.isfile(target):
                check("regression fixture present: %s" % name, False, target)
                continue
            out = os.path.join(outdir, name)
            meta_path = out + ".meta.json"
            proc = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "deflatten.py"), target, out,
                 "--meta", meta_path],
                capture_output=True, text=True)
            check("deflatten exit 0 on %s" % name, proc.returncode == 0, proc.stderr[-300:])
            if not os.path.isfile(meta_path):
                continue
            meta = json.load(open(meta_path))
            check("%s not rolled back" % name, meta.get("rolled_back") is False,
                  meta.get("error"))
            check("%s passes through unchanged" % name,
                  open(out).read() == open(target).read(),
                  "dropped=%s linearised=%s" % (meta.get("dead_branches_dropped"),
                                                meta.get("switch_sequences_linearised")))
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_anonymous_block_qualified():
    """Anonymous helpers get qualified by their nearest named ancestor."""
    print("qualified block names")
    src = ("class K {\n"
           "  _runCheck = (t) => {\n"
           "    const s = function (x) {\n"
           "      let e = 2166136261;\n"
           "      return e;\n"
           "    };\n"
           "    return s(t);\n"
           "  };\n"
           "}\n")
    nl = analyze.line_index(src)
    fn = analyze.enclosing_function(src, src.index("2166136261"), nl)
    check("anonymous helper found", fn is not None)
    if fn:
        check("qualified with named ancestor", fn.get("qualname") == "_runCheck > (anonymous)",
              "got %s" % fn.get("qualname"))


def test_class_field_arrow_named():
    print("class field arrow")
    src = "class K {\n  _runCheck = (t, n) => {\n    return t.charCodeAt(n);\n  };\n}\n"
    nl = analyze.line_index(src)
    fn = analyze.enclosing_function(src, src.index("charCodeAt"), nl)
    check("class field arrow named", fn and fn["name"] == "_runCheck", "got %s" % (fn or {}).get("name"))


def test_multiply_style():
    """A port built from xray.json must match the original JS byte for byte.

    This is the regression that matters most: the guide used to hand out
    (h * PRIME) & 0xFFFFFFFF for every FNV loop, which is only correct when the
    source uses Math.imul. For h * PRIME >>> 0 the product is computed in float64
    on a signed int32 operand, and the digests diverge on longer inputs -- late
    enough that a short smoke test passes.
    """
    print("multiply style detection")
    node, _ver = node_env.resolve()
    if not node:
        check("node available for multiply-style test", False, "no node found")
        return

    outdir = tempfile.mkdtemp(prefix="jx_mul_")
    struct_path = os.path.join(outdir, "structure.json")

    # two files, same algorithm, different multiply -- the only difference that
    # changes the correct port
    trunc_src = ("function hashTrunc(s) {\n"
                 "  var h = 2166136261;\n"
                 "  for (var i = 0; i < s.length; i++) {\n"
                 "    h ^= s.charCodeAt(i);\n"
                 "    h = h * 16777619 >>> 0;\n"
                 "  }\n"
                 "  return h.toString(16);\n"
                 "}\n")
    imul_src = ("function hashImul(s) {\n"
                "  var h = 2166136261;\n"
                "  for (var i = 0; i < s.length; i++) {\n"
                "    h ^= s.charCodeAt(i);\n"
                "    h = Math.imul(h, 16777619) >>> 0;\n"
                "  }\n"
                "  return h.toString(16);\n"
                "}\n")

    styles = {}
    for tag, src in (("trunc", trunc_src), ("imul", imul_src)):
        js = os.path.join(outdir, tag + ".js")
        open(js, "w").write(src)
        subprocess.run([node, os.path.join(SCRIPTS, "structure.mjs"), js, struct_path],
                       capture_output=True)
        st = json.load(open(struct_path))
        data = explain.explain(st)
        algos = data["porting"]["algorithms"]
        styles[tag] = algos[0].get("multiply_style") if algos else None

    check("truncated float multiply detected", styles["trunc"] == "truncated-float",
          "got %s" % styles["trunc"])
    check("imul multiply detected", styles["imul"] == "imul", "got %s" % styles["imul"])

    # the two styles must not hand out the same snippet
    snip_t = report.port_snippet("FNV-1a 32-bit", "truncated-float")
    snip_i = report.port_snippet("FNV-1a 32-bit", "imul")
    check("snippets differ by style", snip_t and snip_i and snip_t != snip_i)
    check("mixed style gets no snippet", report.port_snippet("FNV-1a 32-bit", "mixed") is None)

    # round trip: run the JS, run the snippet, compare
    cases = ["", "a", "Mozilla/5.0 (Macintosh) seed-abc 1234.5678", "x" * 300]
    runner = os.path.join(outdir, "run.mjs")
    open(runner, "w").write(
        trunc_src + imul_src +
        "const cases = " + json.dumps(cases) + ";\n"
        "console.log(JSON.stringify({trunc: cases.map(hashTrunc), imul: cases.map(hashImul)}));\n")
    proc = subprocess.run([node, runner], capture_output=True, text=True)
    ref = json.loads(proc.stdout.strip())

    for tag, snippet in (("trunc", snip_t), ("imul", snip_i)):
        harness = os.path.join(outdir, "port_" + tag + ".py")
        body = "\n".join("    " + ln for ln in snippet.splitlines())
        open(harness, "w").write(
            "import json, sys\n"
            "def digest(data):\n" + body + "\n"
            "    return format(h & 0xFFFFFFFF, 'x')\n"
            "print(json.dumps([digest(c) for c in " + json.dumps(cases) + "]))\n")
        out = subprocess.run([sys.executable, harness], capture_output=True, text=True)
        got = json.loads(out.stdout.strip()) if out.stdout.strip() else None
        check("port matches JS (%s)" % tag, got == ref[tag],
              "py %s vs js %s" % (got, ref[tag]))

    shutil.rmtree(outdir, ignore_errors=True)


# Inputs chosen so that every boundary the UTF-16 / code-point split can hide
# behind is crossed. ASCII and BMP text agree under either reading, which is
# exactly why an ord()-based snippet used to pass: the divergence starts at
# U+10000 and nothing below it can see it.
ASTRAL_CASES = [
    "",                       # empty
    "hello",                  # ASCII
    "\ud7ff",                 # last code point before the surrogate block
    "\ue000",                 # first after it
    "\uffff",                 # last of the BMP: still one unit, still one point
    "\U00010000",             # first astral code point: one point, two units
    "\U0010ffff",             # last assignable code point
    "\U0001f600",             # a single emoji
    "\U0001f600\U0001f680\U0001f4a9",   # several in a row
    "\ud55c\uae00",           # BMP non-ASCII (Hangul) -- must not regress
    "\u4e2d\u6587",           # BMP non-ASCII (CJK)
    "a\U0001f600b\ud55c\U0010ffff\uffff\u4e2dz",  # astral interleaved with BMP
    ("seed-\U0001f984-" + "x" * 40 + "\U0001f600") * 8,  # long mixed string
]


# A JSON \ud83d\ude00 pair is one astral character to JS and to json.loads, but
# two lone surrogates when pasted straight into a Python source literal -- which
# would hand the harness different input than the JS reference got and let an
# ord() loop look correct. So the harnesses below decode their cases with
# json.loads rather than embedding them as literals.
def astral_cases_literal():
    return "json.loads(" + json.dumps(json.dumps(ASTRAL_CASES)) + ")"


def test_astral_char_encoding():
    """The snippet must consume what charCodeAt consumes, not what ord() gives.

    Same shape as test_multiply_style, and the same failure it guards against one
    level down. That test verified how a step is computed and left what is fed
    into it unchecked, which is how a snippet built on "for ch in data: ord(ch)"
    shipped: ord() is a code point, charCodeAt(i) is a UTF-16 code unit, and the
    two are the same number for every character in the BMP. So every ASCII test
    passed, every Hangul and CJK test passed, and the digest changed on the first
    emoji -- the silent-divergence mode this project treats as the worst outcome.

    Both multiply styles are covered, because the encoding is orthogonal to the
    multiply and a fix applied to one snippet only would leave the other wrong.
    """
    print("astral character encoding")
    node, _ver = node_env.resolve()
    if not node:
        check("node available for astral encoding test", False, "no node found")
        return

    outdir = tempfile.mkdtemp(prefix="jx_astral_")
    try:
        struct_path = os.path.join(outdir, "structure.json")

        # charCodeAt in both, so the detected char_source is the same and the only
        # difference is the multiply -- as in test_multiply_style.
        trunc_src = ("function hashTrunc(s) {\n"
                     "  var h = 2166136261;\n"
                     "  for (var i = 0; i < s.length; i++) {\n"
                     "    h ^= s.charCodeAt(i);\n"
                     "    h = h * 16777619 >>> 0;\n"
                     "  }\n"
                     "  return h.toString(16);\n"
                     "}\n")
        imul_src = ("function hashImul(s) {\n"
                    "  var h = 2166136261;\n"
                    "  for (var i = 0; i < s.length; i++) {\n"
                    "    h ^= s.charCodeAt(i);\n"
                    "    h = Math.imul(h, 16777619) >>> 0;\n"
                    "  }\n"
                    "  return h.toString(16);\n"
                    "}\n")

        # the unit has to be read off the source, the same way the multiply is
        sources = {}
        for tag, src in (("trunc", trunc_src), ("imul", imul_src)):
            js = os.path.join(outdir, tag + ".js")
            open(js, "w").write(src)
            subprocess.run([node, os.path.join(SCRIPTS, "structure.mjs"), js, struct_path],
                           capture_output=True)
            st = json.load(open(struct_path))
            data = explain.explain(st)
            algos = data["porting"]["algorithms"]
            sources[tag] = algos[0].get("char_source") if algos else None
            if tag == "imul":
                issues = [p["issue"] for p in data["porting"]["pitfalls"]]
                check("a charCodeAt file gets an encoding pitfall",
                      any("UTF-16" in i for i in issues), issues)

        for tag in ("trunc", "imul"):
            check("charCodeAt detected as utf16 code units (%s)" % tag,
                  sources[tag] == "utf16-code-units", "got %s" % sources[tag])

        # round trip: run the JS, run the snippet we hand out, compare digests
        runner = os.path.join(outdir, "run.mjs")
        open(runner, "w").write(
            trunc_src + imul_src +
            "const cases = " + json.dumps(ASTRAL_CASES) + ";\n"
            "console.log(JSON.stringify({trunc: cases.map(hashTrunc), "
            "imul: cases.map(hashImul)}));\n")
        proc = subprocess.run([node, runner], capture_output=True, text=True)
        ref = json.loads(proc.stdout.strip())

        for tag, style in (("trunc", "truncated-float"), ("imul", "imul")):
            snippet = report.port_snippet("FNV-1a 32-bit", style, sources[tag])
            check("snippet emitted for %s + charCodeAt" % style, bool(snippet))
            if not snippet:
                continue
            harness = os.path.join(outdir, "port_" + tag + ".py")
            body = "\n".join("    " + ln for ln in snippet.splitlines())
            open(harness, "w", encoding="utf-8").write(
                "import json, sys\n"
                "def digest(data):\n" + body + "\n"
                "    return format(h & 0xFFFFFFFF, 'x')\n"
                "print(json.dumps([digest(c) for c in "
                + astral_cases_literal() + "]))\n")
            out = subprocess.run([sys.executable, harness], capture_output=True, text=True)
            got = json.loads(out.stdout.strip()) if out.stdout.strip() else None
            check("astral port matches JS (%s)" % tag, got == ref[tag],
                  "first mismatch: %s" % next(
                      ("%r py=%s js=%s" % (ASTRAL_CASES[i], (got or [])[i:i + 1],
                                           ref[tag][i])
                       for i in range(len(ASTRAL_CASES))
                       if not got or got[i] != ref[tag][i]), "none"))

        # the point of the test: an ord()-per-code-point loop must NOT reproduce
        # these digests, or the test could pass against the bug it exists to catch
        naive = os.path.join(outdir, "naive.py")
        open(naive, "w", encoding="utf-8").write(
            "import json\n"
            "def digest(data):\n"
            "    h = 2166136261\n"
            "    for ch in data:\n"
            "        h ^= ord(ch)\n"
            "        h = (h * 16777619) & 0xFFFFFFFF\n"
            "    return format(h & 0xFFFFFFFF, 'x')\n"
            "print(json.dumps([digest(c) for c in "
            + astral_cases_literal() + "]))\n")
        out = subprocess.run([sys.executable, naive], capture_output=True, text=True)
        naive_got = json.loads(out.stdout.strip()) if out.stdout.strip() else []
        astral = [i for i, c in enumerate(ASTRAL_CASES) if any(ord(x) > 0xFFFF for x in c)]
        check("the cases include astral input", bool(astral), astral)
        check("an ord() loop really fails on the astral cases",
              all(naive_got[i] != ref["imul"][i] for i in astral),
              [ASTRAL_CASES[i] for i in astral if naive_got[i] == ref["imul"][i]])
        # and agrees below U+10000, which is why nothing caught it before
        bmp = [i for i in range(len(ASTRAL_CASES)) if i not in astral]
        check("an ord() loop agrees on every BMP case",
              all(naive_got[i] == ref["imul"][i] for i in bmp),
              [ASTRAL_CASES[i] for i in bmp if naive_got[i] != ref["imul"][i]])

        # a byte-oriented source must not be handed the code-unit snippet
        bytes_src = ("function hashBytes(s) {\n"
                     "  var b = new TextEncoder().encode(s);\n"
                     "  var h = 2166136261;\n"
                     "  for (var i = 0; i < b.length; i++) {\n"
                     "    h ^= b[i];\n"
                     "    h = Math.imul(h, 16777619) >>> 0;\n"
                     "  }\n"
                     "  return h.toString(16);\n"
                     "}\n")
        js = os.path.join(outdir, "bytes.js")
        open(js, "w").write(bytes_src)
        subprocess.run([node, os.path.join(SCRIPTS, "structure.mjs"), js, struct_path],
                       capture_output=True)
        algos = explain.explain(json.load(open(struct_path)))["porting"]["algorithms"]
        byte_source = algos[0].get("char_source") if algos else None
        check("a TextEncoder file is reported as byte-oriented",
              byte_source == "bytes", "got %s" % byte_source)
        byte_snip = report.port_snippet("FNV-1a 32-bit", "imul", byte_source)
        check("the byte snippet encodes instead of walking code units",
              byte_snip and "encode(" in byte_snip and "code_units(" not in byte_snip,
              byte_snip)

        # and with no evidence at all the snippet names its assumption rather
        # than presenting one silently
        unknown = report.port_snippet("FNV-1a 32-bit", "imul", None)
        check("an unknown char source is stated as an assumption",
              unknown and "ASSUMPTION" in unknown, unknown)
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_endpoint_and_storage_recovery():
    """Two facts a reader asks for first: where it calls, and what it remembers.

    An endpoint is almost always hoisted into a module constant, so the fetch call
    site holds a name; and storage is reached as often through window.localStorage
    as through the bare global. Both used to be reported in the unhelpful form: an
    identifier instead of an address, and a persistence read filed as a browser
    property the module fingerprints.
    """
    src = "\n".join([
        'const ENDPOINT = "https://collect.example.test/v2/events";',
        'const KEY = "app.session";',
        "function load() {",
        "  try { return JSON.parse(window.localStorage.getItem(KEY)); }",
        "  catch (e) { return null; }",
        "}",
        "function save(v) { window.localStorage.setItem(KEY, JSON.stringify(v)); }",
        "async function send(payload) {",
        "  return await fetch(ENDPOINT, {",
        '    method: "POST", credentials: "omit",',
        '    headers: { "Content-Type": "application/json" },',
        "    body: JSON.stringify(payload)",
        "  });",
        "}",
        "load(); save({}); send({});",
    ])
    work = tempfile.mkdtemp(prefix="jx_ep_")
    try:
        path = os.path.join(work, "mod.js")
        open(path, "w").write(src)
        out = os.path.join(work, "structure.json")
        node, _ver = node_env.resolve()
        subprocess.run([node, os.path.join(SCRIPTS, "structure.mjs"), path, out],
                       check=True, capture_output=True)
        st = json.load(open(out))

        nets = [n for fn in st["functions"] for n in fn.get("network", [])]
        check("one fetch found", len(nets) == 1, nets)
        check("endpoint resolved through the constant",
              nets[0]["url"] == "https://collect.example.test/v2/events", nets[0]["url"])
        check("call-site expression kept", nets[0].get("url_expression") == "ENDPOINT",
              nets[0].get("url_expression"))

        by_name = {fn.get("name"): fn for fn in st["functions"]}
        check("window-prefixed storage recorded",
              any(s.startswith("localStorage") for s in by_name["load"]["storage"]),
              by_name["load"]["storage"])

        exp = explain.explain(st)
        roles = {f["name"]: [r["role"] for r in f["roles"]] for f in exp["functions"]}
        check("storage reader is persistence, not fingerprinting",
              "persistence" in roles.get("load", []),
              roles.get("load"))
        props = [i["property"] for i in exp["porting"]["inputs"]]
        check("storage is not listed as a fingerprint input",
              not any("localStorage" in p for p in props), props)
        check("endpoint in the summary",
              "https://collect.example.test/v2/events" in exp["summary"]["endpoints"],
              exp["summary"]["endpoints"])
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_reachability_ignores_flow_budget():
    """Code only the bundle wrapper can reach must not be reported as dead.

    Flows are truncated to stay readable, but that budget is a presentation
    limit. When it also decided reachability, the function performing the only
    fetch in the Sentinel sample came out as unreachable, which points a reader
    away from the request the module actually makes.
    """
    print("reachability")
    node, _ver = node_env.resolve()
    if not node:
        check("node available for reachability test", False, "no node found")
        return

    outdir = tempfile.mkdtemp(prefix="jx_reach_")
    js = os.path.join(outdir, "wrapped.js")
    struct_path = os.path.join(outdir, "structure.json")

    # the shape that broke: a wrapper IIFE holds a deep anonymous chain, and only
    # the innermost closure calls the function that does the request
    open(js, "w").write(
        "(function () {\n"
        "  async function send(payload) {\n"
        "    return fetch('https://example.test/api', {method: 'POST', body: payload});\n"
        "  }\n"
        "  setTimeout(function () {\n"
        "    [1].forEach(function () {\n"
        "      send('x');\n"
        "    });\n"
        "  }, 0);\n"
        "})();\n")
    subprocess.run([node, os.path.join(SCRIPTS, "structure.mjs"), js, struct_path],
                   capture_output=True)
    st = json.load(open(struct_path))
    data = explain.explain(st)

    net = [f for f in data["functions"] if f.get("network")]
    check("network function found", bool(net), "no network function in output")
    if net:
        check("network function reachable", net[0]["reachable_from_entry"],
              "%s marked unreachable" % net[0]["name"])
    check("wrapper not an entry point",
          all("L1-" not in e["name"] for e in data["entry_points"]),
          "entries %s" % [e["name"] for e in data["entry_points"]])

    shutil.rmtree(outdir, ignore_errors=True)



def test_pipeline_log_records_failure():
    """A failed stage must still show up in pipeline.json, not just on stderr.

    Points --anchors at a path that does not exist. load_anchors() calls
    open() on it directly and lets FileNotFoundError propagate, so the anchor
    scan stage exits non-zero after deobfuscate/inline/deflatten/structure/explain
    have already succeeded -- the shape that used to lose everything to stderr.
    """
    print("pipeline log on stage failure")
    fixture = os.path.join(ROOT, "fixtures", "sample_obfuscated.js")
    if not os.path.isfile(fixture):
        check("fixture present for failure test", False, fixture)
        return

    outdir = tempfile.mkdtemp(prefix="jsxray_fail_")
    missing_anchors = os.path.join(outdir, "does_not_exist_anchors.json")
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "xray.py"), fixture, "-o", outdir,
             "--anchors", missing_anchors],
            capture_output=True, text=True)
        check("pipeline exits non-zero on stage failure", proc.returncode == 1, proc.returncode)

        pipeline_path = os.path.join(outdir, "pipeline.json")
        check("pipeline.json still written on failure", os.path.isfile(pipeline_path), pipeline_path)
        if not os.path.isfile(pipeline_path):
            return

        pipeline = json.load(open(pipeline_path))
        stages = pipeline.get("stages", [])
        # deobfuscate, inline, deflatten, structure, explain succeeded; anchor
        # scan failed and stopped the run, so report/TOON never executed and
        # never appear.
        check("failed run stops at the failing stage", len(stages) == 6,
              [s.get("label") for s in stages])
        if len(stages) != 6:
            return
        check("stages before the failure all ok",
              all(s.get("ok") is True for s in stages[:5]),
              [(s.get("label"), s.get("ok")) for s in stages[:5]])
        failed = stages[5]
        check("failing stage is the anchor scan", "anchor" in failed.get("label", ""),
              failed.get("label"))
        check("failing stage recorded ok=False", failed.get("ok") is False, failed)
        check("failing stage still has cmd/meta fields",
              "cmd" in failed and "meta" in failed, failed)
        check("failing stage cmd references the missing anchors file",
              any(missing_anchors in str(part) for part in (failed.get("cmd") or [])),
              failed.get("cmd"))
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_toon_stage():
    """The TOON stage must run unconditionally and produce a decodable xray.toon.

    Running the full pipeline (webcrack included) just to exercise this stage
    would be slow and redundant with test_pipeline_end_to_end. Instead this
    calls toon_stats.py directly against the checked-in xray.json sample, which
    is what the orchestrator does as its last step -- see xray.py's "encode
    TOON" stage.
    """
    print("toon encode stage")
    sample = os.path.join(ROOT, "tests", "samples", "xray_sentinel_sdk", "xray.json")
    if not os.path.isfile(sample):
        check("xray_sentinel_sdk/xray.json present", False, sample)
        return

    outdir = tempfile.mkdtemp(prefix="jsxray_toon_")
    toon_path = os.path.join(outdir, "xray.toon")
    stats_path = os.path.join(outdir, "toon_stats.json")
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "toon_stats.py"), sample, toon_path, "--stats", stats_path],
        capture_output=True, text=True)
    check("toon stage exit 0", proc.returncode == 0, proc.stderr[-400:])
    check("xray.toon written", os.path.isfile(toon_path))
    check("toon_stats.json written", os.path.isfile(stats_path))

    if not (os.path.isfile(toon_path) and os.path.isfile(stats_path)):
        shutil.rmtree(outdir, ignore_errors=True)
        return

    stats = json.load(open(stats_path))
    for key in ("json_chars", "toon_chars", "char_reduction_pct",
                "json_tokens", "toon_tokens", "token_reduction_pct", "tokenizer"):
        check("stats has %s" % key, key in stats, stats)
    check("toon is smaller than json", stats["toon_chars"] < stats["json_chars"],
          "toon=%s json=%s" % (stats.get("toon_chars"), stats.get("json_chars")))
    check("char reduction is positive", stats["char_reduction_pct"] > 0, stats["char_reduction_pct"])
    if stats["tokenizer"] is None:
        # tiktoken not installed in this environment -- confirm the fallback is
        # explicit rather than a silently-null token field
        check("token fields null without tiktoken",
              stats["json_tokens"] is None and stats["toon_tokens"] is None and
              stats["token_reduction_pct"] is None, stats)
        check("fallback noted on stderr", "tiktoken not installed" in proc.stderr, proc.stderr[-400:])
    else:
        check("token reduction is positive", stats["token_reduction_pct"] > 0, stats["token_reduction_pct"])

    # round-trip xray.toon back against the real xray.json through the reference decoder
    node = shutil.which("node")
    decode_cli = os.path.join(ROOT, "skill", "tests", "_toon_ref_decode.mjs")
    if node and os.path.isfile(decode_cli):
        probe = subprocess.run([node, decode_cli], input="a: 1", capture_output=True, text=True,
                                cwd=os.path.dirname(decode_cli))
        if probe.returncode == 0:
            toon_text = open(toon_path, encoding="utf-8").read()
            dec = subprocess.run([node, decode_cli], input=toon_text, capture_output=True, text=True)
            check("xray.toon decodes via reference decoder", dec.returncode == 0, dec.stderr[-400:])
            if dec.returncode == 0:
                decoded = json.loads(dec.stdout)
                original = json.load(open(sample))
                check("xray.toon round-trips to xray.json", decoded == original,
                      "structural mismatch (see diff manually; both are large)")
        else:
            check("reference decoder resolvable for toon stage test", False,
                  "run 'npm install' at the repo root\n" + probe.stderr[-400:])
    else:
        check("reference decoder available for toon stage test", False,
              "node=%r decode_cli_exists=%s -- skipping round-trip check" %
              (node, os.path.isfile(decode_cli)))

    shutil.rmtree(outdir, ignore_errors=True)


def test_vm_detection_positive():
    """A bytecode interpreter must be called out, not analyzed as if it were logic.

    JSVMP compiles the original logic into a bytecode array and leaves only the
    interpreter in the source. The pipeline still succeeds on such a file and
    still fills in flows and functions -- all of them interpreter internals -- so
    without this verdict the run looks like an ordinary success and the reader
    never learns the result describes a virtual machine.
    """
    print("vm detection: positive")
    fixture = os.path.join(ROOT, "fixtures", "vmp_interpreter.js")
    if not os.path.isfile(fixture):
        check("vmp fixture present", False, fixture)
        return

    data, err = structure.extract(fixture)
    if err:
        check("structure ran for the vmp fixture", False, err)
        return

    vm = data.get("vm_signals") or {}
    check("vmp fixture judged vm-obfuscated", vm.get("verdict") == "vm-obfuscated",
          "got %r (score %s, %s)" % (vm.get("verdict"), vm.get("score"),
                                     [s["kind"] for s in vm.get("signals", [])]))

    kinds = {s["kind"] for s in vm.get("signals", [])}
    # the two signals a verdict of vm-obfuscated is required to rest on
    check("masked dispatch switch found", "masked-switch-dispatch" in kinds, kinds)
    check("numeric jump writes found", "dense-numeric-jumps" in kinds, kinds)
    check("score reflects both core signals", (vm.get("score") or 0) >= 70, vm.get("score"))

    # every signal must carry evidence a reader can check, not just a label
    for sig in vm.get("signals", []):
        check("signal %s carries a detail" % sig.get("kind"),
              bool(sig.get("detail")), sig)
    dispatch = [s for s in vm.get("signals", []) if s["kind"] == "masked-switch-dispatch"]
    check("dispatch signal cites a line", dispatch and dispatch[0].get("line"),
          dispatch)


def test_vm_detection_no_false_positives():
    """The cost of a false positive is higher than a miss, so this is the gate.

    Calling an ordinary obfuscated file VM-obfuscated teaches a reader to
    disbelieve results that were correct, which is worse than the silence this
    detector replaces. sentinel_sdk.js is the case that matters: a real anti-bot
    SDK, genuinely obfuscated, with a string array and deep closure nesting --
    but not a bytecode VM. state_machine.js is the near-miss shape: a big switch
    inside a loop, which is what control-flow flattening and hand-written
    tokenizers both look like.
    """
    print("vm detection: no false positives")
    clean_files = [
        ("sentinel_sdk.js", os.path.join(ROOT, "tests", "samples", "sentinel_sdk.js")),
        ("sample_obfuscated.js", os.path.join(ROOT, "fixtures", "sample_obfuscated.js")),
        ("multi_scope_arrays.js", os.path.join(ROOT, "fixtures", "multi_scope_arrays.js")),
        ("state_machine.js", os.path.join(ROOT, "fixtures", "state_machine.js")),
    ]
    for label, path in clean_files:
        if not os.path.isfile(path):
            check("%s present" % label, False, path)
            continue
        data, err = structure.extract(path)
        if err:
            check("structure ran for %s" % label, False, err)
            continue
        vm = data.get("vm_signals") or {}
        check("%s not flagged as VM" % label, vm.get("verdict") == "none",
              "got %r (score %s, %s)" % (vm.get("verdict"), vm.get("score"),
                                         [s["kind"] for s in vm.get("signals", [])]))
        # A clean file must also produce no warning downstream, since that is
        # what a reader actually sees.
        exp = explain.explain(data)
        check("%s summary reports no VM" % label,
              exp["summary"]["vm_obfuscation"] == "none",
              exp["summary"]["vm_obfuscation"])
        check("%s gets no VM confidence note" % label,
              not any("VM-obfusc" in n for n in exp["confidence_notes"]),
              exp["confidence_notes"][:1])


def test_vm_warning_reaches_outputs():
    """The verdict is only useful if it reaches what a caller reads.

    Three consumers, three places it has to appear: an agent reads
    summary.vm_obfuscation, an agent or human reading the notes must hit the
    warning first rather than after three ordinary caveats, and a human opening
    report.md must see it above the findings instead of below them.
    """
    print("vm warning propagation")
    fixture = os.path.join(ROOT, "fixtures", "vmp_interpreter.js")
    if not os.path.isfile(fixture):
        check("vmp fixture present for propagation test", False, fixture)
        return

    outdir = tempfile.mkdtemp(prefix="jsxray_vm_")
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "xray.py"), fixture, "-o", outdir],
            capture_output=True, text=True)
        check("vm pipeline exit 0", proc.returncode == 0, proc.stderr[-400:])

        xray_path = os.path.join(outdir, "xray.json")
        check("xray.json written for vm file", os.path.isfile(xray_path), xray_path)
        if not os.path.isfile(xray_path):
            return
        data = json.load(open(xray_path))

        check("summary carries the machine-readable verdict",
              data["summary"].get("vm_obfuscation") == "vm-obfuscated",
              data["summary"].get("vm_obfuscation"))
        check("vm_signals travel with the verdict as evidence",
              (data.get("vm_signals") or {}).get("signals"), data.get("vm_signals"))

        notes = data.get("confidence_notes") or []
        check("VM warning is the first confidence note",
              notes and "VM-obfuscated" in notes[0], notes[:1])
        check("warning says the functions are interpreter internals",
              notes and "interpreter" in notes[0], notes[:1])
        check("ordinary notes are kept alongside it", len(notes) == 4, len(notes))

        rep_path = os.path.join(outdir, "report.md")
        check("report.md written for vm file", os.path.isfile(rep_path), rep_path)
        if os.path.isfile(rep_path):
            rep = open(rep_path).read()
            check("report warns about VM obfuscation", "VM-obfuscated" in rep)
            # above the findings: a warning under "Key functions" is a warning
            # nobody reads before trusting them
            warn_at = rep.find("VM-obfuscated")
            check("warning precedes the summary table", warn_at < rep.find("| functions |"),
                  "warning at %s, table at %s" % (warn_at, rep.find("| functions |")))
            check("warning precedes the flows", warn_at < rep.find("## Flows"),
                  "warning at %s, flows at %s" % (warn_at, rep.find("## Flows")))
            check("report lists the signals as evidence",
                  "masked-switch-dispatch" in rep and "dense-numeric-jumps" in rep)

        # the run must not look like an ordinary success on stderr either
        check("stderr warns about the VM verdict", "VM obfuscation" in proc.stderr,
              proc.stderr[-300:])
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


SAMPLE_XRAYJS = os.path.join(ROOT, "tests", "samples", "xray_sentinel_sdk")


def run_xq(*argv):
    """xq as a subprocess, so the tests exercise the CLI a caller actually runs."""
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "xq.py")] + list(argv),
                          capture_output=True, text=True)


def run_xq_in(cwd, *argv):
    """xq with a chosen working directory, for the cases where cwd is the input."""
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "xq.py")] + list(argv),
                          capture_output=True, text=True, cwd=cwd)


def _roles_by_name(fixture):
    """Run structure + classify over a fixture and return {display_name: [roles]}.

    Goes through explain.classify directly rather than the whole pipeline where
    possible, so a failure points at the classifier instead of at webcrack.
    """
    data, err = structure.extract(fixture)
    if err:
        return None, err
    by_id = explain.build_index(data)
    out = {}
    for fn in data.get("functions", []) or []:
        out[explain.display_name(fn, by_id)] = explain.classify(fn, by_id)
    return out, None


def _anti_analysis_names(roles_by_name):
    return sorted(n for n, rs in roles_by_name.items()
                  if any(r["role"] == explain.ANTI_ANALYSIS_ROLE for r in rs))


def _role_counts(fixture):
    """Role counts over every function in a fixture.

    Not derived from _roles_by_name: that map is keyed by display name, and
    obfuscated files reuse names freely, so counting its values undercounts.
    """
    return _roles_without_anti_analysis(fixture, include_anti_analysis=True)


def _roles_without_anti_analysis(fixture=None, structure_json=None,
                                 include_anti_analysis=False):
    """Role counts as if the anti-analysis rule did not exist.

    Used to measure the rule's effect in-process instead of comparing against a
    number written down from one earlier run. Pass structure_json to score the
    same facts a pipeline run scored: the counts depend on how much webcrack
    undid, so a baseline taken from the raw file would not be comparable to a
    summary.roles taken from clean.js.
    """
    if structure_json is not None:
        with open(structure_json, encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data, err = structure.extract(fixture)
        if err:
            return None
    by_id = explain.build_index(data)
    original = explain.anti_analysis_role
    if not include_anti_analysis:
        explain.anti_analysis_role = lambda fn: None
    try:
        counts = {}
        for fn in data.get("functions", []) or []:
            for r in explain.classify(fn, by_id):
                counts[r["role"]] = counts.get(r["role"], 0) + 1
    finally:
        explain.anti_analysis_role = original
    return counts


def test_anti_analysis_positive():
    """Obfuscator self-defending / debug-protection stubs must be labelled.

    fixtures/anti_analysis_stubs.js is real javascript-obfuscator 4.1.1 output
    (selfDefending + debugProtection + disableConsoleOutput) whose stub shapes
    were perturbed so webcrack's exact-AST matchers no longer remove them --
    which is the case a user hit, where the stubs were plainly in the file. See
    the fixture header for how it was produced.

    The stubs are labelled rather than deleted: dropping the functions would
    leave a reader unable to check the call, the same reason vm_signals warns
    instead of removing an interpreter.
    """
    print("anti-analysis: positive")
    fixture = os.path.join(ROOT, "fixtures", "anti_analysis_stubs.js")
    if not os.path.isfile(fixture):
        check("anti-analysis fixture present", False, fixture)
        return

    roles_by_name, err = _roles_by_name(fixture)
    if err:
        check("structure ran for the anti-analysis fixture", False, err)
        return

    tagged = _anti_analysis_names(roles_by_name)
    # 4 stubs: the self-defending toString check, the debug-protection source
    # assertion, the console override, and the recursive debugger trap.
    check("all four stub shapes tagged", len(tagged) == 4,
          "got %d: %s" % (len(tagged), tagged))

    evidence_kinds = []
    for name in tagged:
        for r in roles_by_name[name]:
            if r["role"] != explain.ANTI_ANALYSIS_ROLE:
                continue
            check("stub %s carries evidence" % name, bool(r["evidence"]), r)
            check("stub %s has a real confidence" % name,
                  r["confidence"] in ("high", "medium"), r["confidence"])
            evidence_kinds.extend(r["evidence"])

    joined = " | ".join(evidence_kinds)
    # each required-tier signal shows up somewhere, named in the evidence so a
    # reader can find the construct in the source rather than take the label
    check("debugger trap cited", "debugger" in joined, joined)
    check("source self-check cited", "own source text" in joined, joined)
    check("console override cited", "console methods" in joined, joined)

    # the real logic keeps its own roles: the point is to separate scaffolding
    # from findings, not to relabel the module
    def roles_of(name):
        return {r["role"] for r in roles_by_name.get(name, [])}

    check("hash keeps hash/digest", "hash/digest" in roles_of("computeToken"),
          roles_of("computeToken"))
    check("collector keeps fingerprinting",
          "environment fingerprinting" in roles_of("collectProfile"),
          roles_of("collectProfile"))
    check("reporter keeps network transport",
          "network transport" in roles_of("report"), roles_of("report"))
    check("persister keeps persistence",
          "persistence" in roles_of("persist"), roles_of("persist"))
    # the validator throws, and that finding must survive: the role exists to
    # stop scaffolding from being read as validation, not the other way round
    check("real validator keeps validation/error path",
          "validation/error path" in roles_of("validateProfile"),
          roles_of("validateProfile"))
    check("real validator is not called scaffolding",
          explain.ANTI_ANALYSIS_ROLE not in roles_of("validateProfile"),
          roles_of("validateProfile"))


def test_anti_analysis_no_false_positives():
    """The gate. A false positive here removes a finding instead of adding one.

    Normal code hooks console, measures time and validates with regexes. Tagging
    on any one of those would relabel a module's real error handling as
    obfuscator boilerplate, and a reader told a function is boilerplate stops
    reading it. So this checks the two files that must stay clean plus the
    lookalike fixture, where every keyed-on behaviour appears in benign form.
    """
    print("anti-analysis: no false positives")

    # sentinel_sdk.js is a real anti-bot SDK. It does contain 9 genuine
    # javascript-obfuscator self-defending stubs (verbatim
    # "X.toString().search(...)" checks, verifiable in clean.js), so the
    # assertion is not "zero tags" -- that would be false. What must hold is
    # that no function carrying real behaviour is relabelled.
    sentinel = os.path.join(ROOT, "tests", "samples", "sentinel_sdk.js")
    if os.path.isfile(sentinel):
        roles_by_name, err = _roles_by_name(sentinel)
        if err:
            check("structure ran for sentinel_sdk", False, err)
        else:
            tagged = set(_anti_analysis_names(roles_by_name))
            # every tag sits on an anonymous callback -- the stub shape -- and
            # none of them carries a second, behavioural role
            for name in tagged:
                others = {r["role"] for r in roles_by_name[name]
                          if r["role"] not in (explain.ANTI_ANALYSIS_ROLE,
                                               "unclassified")}
                check("sentinel tag %s displaces no finding" % name,
                      not others, others)
            # Every other role keeps exactly the count it had before this role
            # existed. Measured against a baseline computed in the same process
            # rather than a hardcoded number: the absolute counts depend on how
            # much webcrack managed to undo, and a literal here would encode one
            # run of that instead of the property being tested, which is that
            # nothing moved out of a behavioural bucket.
            counts = _role_counts(sentinel)
            baseline = _roles_without_anti_analysis(sentinel)
            if baseline is None:
                check("baseline classification ran for sentinel_sdk", False, "")
            else:
                moved = {role: (baseline.get(role, 0), counts.get(role, 0))
                         for role in set(baseline) | set(counts)
                         if role not in (explain.ANTI_ANALYSIS_ROLE,
                                         "unclassified")
                         and baseline.get(role, 0) != counts.get(role, 0)}
                check("no behavioural role changed count on sentinel_sdk",
                      not moved, moved)
                # and the functions the label did claim came out of the
                # unclassified pile, which is the only acceptable source
                check("tagged sentinel functions were previously unclassified",
                      counts.get(explain.ANTI_ANALYSIS_ROLE, 0) ==
                      baseline.get("unclassified", 0) - counts.get("unclassified", 0),
                      (baseline.get("unclassified"), counts.get("unclassified"),
                       counts.get(explain.ANTI_ANALYSIS_ROLE)))

    # multi_scope_arrays.js is obfuscated but carries none of these stubs: an
    # obfuscated file must not be tagged merely for being obfuscated.
    multi = os.path.join(ROOT, "fixtures", "multi_scope_arrays.js")
    if os.path.isfile(multi):
        roles_by_name, err = _roles_by_name(multi)
        if err:
            check("structure ran for multi_scope_arrays", False, err)
        else:
            tagged = _anti_analysis_names(roles_by_name)
            check("multi_scope_arrays gets no anti-analysis role",
                  not tagged, tagged)

    # the lookalike fixture: console hooking, performance.now timing, a
    # toString()+regex source inspection, a throwing validator and recursion,
    # each in its legitimate form
    benign = os.path.join(ROOT, "fixtures", "benign_lookalikes.js")
    if not os.path.isfile(benign):
        check("benign lookalike fixture present", False, benign)
        return
    roles_by_name, err = _roles_by_name(benign)
    if err:
        check("structure ran for benign_lookalikes", False, err)
        return

    tagged = _anti_analysis_names(roles_by_name)
    check("benign lookalikes get no anti-analysis role", not tagged, tagged)

    roles_of = lambda n: {r["role"] for r in roles_by_name.get(n, [])}
    # the finding this role must never eat
    check("benign validator keeps validation/error path",
          "validation/error path" in roles_of("validateRecord"),
          roles_of("validateRecord"))

    # and the individual behaviours, spelled out so a future loosening of the
    # rule fails here with the reason attached
    for name, why in (
        ("installLogger", "hooks console.log/warn/error like a logger"),
        ("timeOperation", "measures elapsed time with performance.now"),
        ("describeFunction", "calls toString() and matches it with a regex"),
        ("retryWithBackoff", "recurses"),
    ):
        check("not tagged though it %s: %s" % (why, name),
              explain.ANTI_ANALYSIS_ROLE not in roles_of(name),
              roles_of(name))


def test_anti_analysis_requires_more_than_one_behaviour():
    """The required/corroborating split, checked on synthetic facts.

    classify() is fed structure-shaped dicts directly here so each rule can be
    exercised in isolation: going through a .js fixture for every case would
    make it unclear which condition fired.
    """
    print("anti-analysis: signal combination rules")

    def fn(**kw):
        base = {"id": "fn0", "name": None, "kind": "function", "calls": [],
                "globals": [], "strings": [], "numbers": [], "algorithms": [],
                "operators": [], "returns": [], "throws": [], "params": [],
                "control": {"loops": 0, "branches": 0, "try_blocks": 0,
                            "switches": 0},
                "loc_lines": 5, "start_line": 1, "end_line": 5}
        base.update(kw)
        return base

    # corroborating signals alone claim nothing: the global-object preamble
    # appears in ordinary universal-module wrappers
    only_global = fn(strings=['return (function() {}.constructor("return this")( ));'])
    check("global-object preamble alone is not enough",
          explain.anti_analysis_role(only_global) is None,
          explain.anti_analysis_role(only_global))

    # self-recursion alone is not enough either
    only_recursion = fn(name="walk", calls=["walk"])
    check("self-recursion alone is not enough",
          explain.anti_analysis_role(only_recursion) is None,
          explain.anti_analysis_role(only_recursion))

    # a partial console hook is not the disableConsoleOutput sweep
    small_hook = fn(strings=["log", "warn", "error"])
    check("hooking three console methods is not enough",
          explain.anti_analysis_role(small_hook) is None,
          explain.anti_analysis_role(small_hook))

    # the obfuscator's self-check literal held as *data* is not a check being
    # run. This is the string-array provider case: it returns its table and
    # makes no calls, and tagging it took out the Sentinel SDK's own decoders.
    pattern_as_data = fn(strings=["bind", "apply", "search", "(((.+)+)+)+$"],
                         returns=["(s = function () { return t; })()"])
    check("holding the self-check pattern as data is not enough",
          explain.anti_analysis_role(pattern_as_data) is None,
          explain.anti_analysis_role(pattern_as_data))

    # the same literal with a call that applies it is the stub
    pattern_executed = fn(calls=["a.toString"], strings=["(((.+)+)+)+$"],
                          returns=['a.toString().search("(((.+)+)+)+$")'])
    role = explain.anti_analysis_role(pattern_executed)
    check("pattern plus toString/search is tagged", role is not None, role)
    if role:
        check("executed self-check reads high", role["confidence"] == "high",
              role)

    # a bare debugger statement is a required signal, but alone it stays medium:
    # a hand-written debugger trap is something a reader may still want to see
    bare_debugger = fn(debugger_statements=1)
    role = explain.anti_analysis_role(bare_debugger)
    check("bare debugger statement is tagged", role is not None, role)
    if role:
        check("lone required signal stays medium",
              role["confidence"] == "medium", role)

    # a full console sweep is on its own sufficient but not high
    full_hook = fn(strings=list(explain.CONSOLE_HOOK_METHODS))
    role = explain.anti_analysis_role(full_hook)
    check("full console sweep is tagged", role is not None, role)

    # two required signals together are the full fingerprint
    trap = fn(name="t", calls=["t"], debugger_statements=1,
              strings=["debugger", "while (true) {}"])
    role = explain.anti_analysis_role(trap)
    check("debugger statement plus trap literals reads high",
          role is not None and role["confidence"] == "high", role)


def test_anti_analysis_role_is_not_inherited():
    """The label must stay on the function that holds the trap.

    rollup_child_roles lifts a nested closure's role to its parent, which is
    right for a hash loop in a callback and wrong here: obfuscator stubs are
    siblings of the real logic, so the nearest enclosing function is usually the
    bundle wrapper spanning the whole file. Propagating the label there would
    mark the entire module as scaffolding and tell a reader to skip the code
    they came for -- worse than not labelling at all.
    """
    print("anti-analysis: never inherited upwards")
    fixture = os.path.join(ROOT, "fixtures", "anti_analysis_stubs.js")
    if not os.path.isfile(fixture):
        check("anti-analysis fixture present for rollup test", False, fixture)
        return

    data, err = structure.extract(fixture)
    if err:
        check("structure ran for the rollup test", False, err)
        return

    fns = data.get("functions", []) or []
    by_id = explain.build_index(data)
    roles_by_id = {fn["id"]: explain.classify(fn, by_id) for fn in fns}
    direct = {fid for fid, rs in roles_by_id.items()
              if any(r["role"] == explain.ANTI_ANALYSIS_ROLE for r in rs)}
    explain.rollup_child_roles(fns, by_id, roles_by_id)
    after = {fid for fid, rs in roles_by_id.items()
             if any(r["role"] == explain.ANTI_ANALYSIS_ROLE for r in rs)}

    check("rollup adds no anti-analysis holders", direct == after,
          "gained %s" % sorted(after - direct))
    for fid, rs in roles_by_id.items():
        for r in rs:
            if r["role"] == explain.ANTI_ANALYSIS_ROLE:
                check("anti-analysis role is a direct observation",
                      not r.get("inherited_from"), r)


def test_anti_analysis_improves_the_histogram():
    """Measure the effect on summary.roles rather than assert it improved.

    Runs the full pipeline so the numbers are the ones a caller actually sees in
    xray.json, and prints them so a regression shows the shift instead of only a
    boolean.
    """
    print("anti-analysis: histogram effect")
    fixture = os.path.join(ROOT, "fixtures", "anti_analysis_stubs.js")
    if not os.path.isfile(fixture):
        check("anti-analysis fixture present for histogram test", False, fixture)
        return

    outdir = tempfile.mkdtemp(prefix="xray-anti-")
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "xray.py"), fixture,
             "-o", outdir],
            capture_output=True, text=True)
        xray_json = os.path.join(outdir, "xray.json")
        if proc.returncode != 0 or not os.path.isfile(xray_json):
            check("pipeline ran on the anti-analysis fixture", False,
                  proc.stderr[-400:])
            return
        summary = json.load(open(xray_json))["summary"]
        roles = summary.get("roles") or {}
        print("    roles: %s" % json.dumps(roles, sort_keys=True))

        tagged = roles.get(explain.ANTI_ANALYSIS_ROLE, 0)
        check("scaffolding is counted separately in summary.roles",
              tagged == 4, "got %s" % tagged)

        # The fixture holds 6 real functions and the surviving stubs inflate the
        # file well past that, so the property worth checking is that each
        # behavioural bucket still counts exactly the one real function that
        # earns it -- scaffolding is not hiding inside any of them.
        check("hash/digest still counts one function",
              roles.get("hash/digest") == 1, roles)
        check("network transport still counts one function",
              roles.get("network transport") == 1, roles)
        # exactly the one real validator. This is the number from the report
        # that prompted the role: stubs that throw to break out of their own
        # recursion were being counted here as though they were input validation.
        check("validation/error path counts only the real validator",
              roles.get("validation/error path") == 1, roles)

        # The measured shift, so a regression shows the movement rather than a
        # bare False. Everything the label claimed has to come out of
        # unclassified and nowhere else.
        baseline = _roles_without_anti_analysis(
            structure_json=os.path.join(outdir, "structure.json"))
        if baseline is not None:
            print("    baseline: %s" % json.dumps(baseline, sort_keys=True))
            moved = {role: (baseline.get(role, 0), roles.get(role, 0))
                     for role in set(baseline) | set(roles)
                     if role not in (explain.ANTI_ANALYSIS_ROLE, "unclassified")
                     and baseline.get(role, 0) != roles.get(role, 0)}
            check("no behavioural role changed count on the fixture",
                  not moved, moved)
            check("the label only claimed previously unclassified functions",
                  tagged == baseline.get("unclassified", 0) - roles.get("unclassified", 0),
                  (baseline.get("unclassified"), roles.get("unclassified"), tagged))

        # the label has to reach the artifact with its evidence, not just the
        # histogram, or a reader cannot check it
        detailed = json.load(open(xray_json))["functions"]
        with_role = [f for f in detailed
                     if any(r["role"] == explain.ANTI_ANALYSIS_ROLE
                            for r in f.get("roles") or [])]
        check("tagged stubs appear in functions[] with evidence",
              with_role and all(
                  r.get("evidence")
                  for f in with_role for r in f["roles"]
                  if r["role"] == explain.ANTI_ANALYSIS_ROLE),
              [f["name"] for f in with_role])
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def test_xq_subcommands():
    """Every subcommand has to answer on a real analysis, not just parse its args."""
    print("xq subcommands")
    if not os.path.isdir(SAMPLE_XRAYJS):
        check("sample .xrayjs present", False, SAMPLE_XRAYJS)
        return

    cases = [
        ("summary", ["summary"], ["functions 220", "network transport", "caveats:"]),
        ("find by name", ["find", "getConfig"], ["fn56", "_.getConfig", "L316"]),
        ("find is regex", ["find", "^on$"], ["fn197"]),
        ("find literals", ["find", "sentinel", "--strings"], ["backend-api/sentinel"]),
        ("show by name", ["show", "on"],
         ["fn197", "network transport", "async on(t, n)", "await fetch"]),
        ("show by id", ["show", "fn49"], ["FNV-1a 32-bit", "hash/digest"]),
        ("callers", ["callers", "on"], ["callers of fn197", "via on", "resolution"]),
        ("callees", ["callees", "on"], ["fn195", "rn"]),
        ("callers depth", ["callers", "fn195", "--depth", "2"], ["fn197"]),
        ("flow", ["flow", "fn49"], ["flow[0]", "_.getEnforcementTokenSync", "fn49"]),
        ("port all", ["port"],
         ["FNV-1a 32-bit", "multiply:  imul", "inputs a port must supply",
          "pitfall:", "fetch POST"]),
        ("port one algorithm", ["port", "FNV"], ["fn49", "2166136261"]),
        ("grep", ["grep", "fetch"], ["1106", "fn197", "on"]),
        ("entries", ["entries", "--traced"], ["fn41", "traced"]),
        ("roles histogram", ["roles"], ["network transport"]),
        ("roles filtered", ["roles", "hash"], ["fn49", "hash/digest"]),
    ]
    for label, argv, needles in cases:
        proc = run_xq(SAMPLE_XRAYJS, *argv)
        check("xq %s exits 0" % label, proc.returncode == 0, proc.stderr[-300:])
        for needle in needles:
            check("xq %s says %r" % (label, needle), needle in proc.stdout,
                  proc.stdout[:200])

    # --json has to parse for every command: it is the contract anything
    # scripting against xq depends on
    for argv in (["summary"], ["find", "on"], ["show", "on"], ["callers", "on"],
                 ["callees", "on"], ["flow", "fn49"], ["port"], ["grep", "fetch"],
                 ["entries"], ["roles", "hash"]):
        proc = run_xq(SAMPLE_XRAYJS, "--json", *argv)
        ok = proc.returncode == 0
        detail = proc.stderr[-200:]
        try:
            json.loads(proc.stdout)
        except ValueError as exc:
            ok, detail = False, str(exc)
        check("xq --json %s is valid json" % argv[0], ok, detail)

    # source is the point of show: the real clean.js slice, truncated by default
    # rather than dumping a 200-line function into the answer
    clean = open(os.path.join(SAMPLE_XRAYJS, "clean.js")).read().splitlines()
    got = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "show", "fn197", "--full").stdout)
    start, end = got["lines"]
    check("show --full returns the exact clean.js slice",
          got["source"] == clean[start - 1:end],
          "%d lines vs %d" % (len(got["source"]), end - start + 1))
    check("show --full omits nothing", got["source_omitted"] == 0, got["source_omitted"])
    trunc = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "show", "fn0").stdout)
    check("show truncates a long function by default",
          len(trunc["source"]) == xq.SRC_LIMIT and trunc["source_omitted"] > 0,
          "%d lines, %d omitted" % (len(trunc["source"]), trunc["source_omitted"]))

    # an ambiguous name lists candidates instead of silently picking one
    proc = run_xq(SAMPLE_XRAYJS, "show", "s")
    check("ambiguous name lists candidates", "re-run with an id" in proc.stdout,
          proc.stdout[:200])
    check("ambiguous name names the ids",
          "fn1" in proc.stdout and "fn2" in proc.stdout, proc.stdout[:200])

    # grep attributing a hit to the innermost enclosing function is the whole
    # reason to use it over grep(1): fn49 is the iife inside _._runCheck
    hits = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "grep", "Math.imul").stdout)["hits"]
    check("grep found the imul site", bool(hits), hits)
    check("grep attributes imul to the inner iife, not its enclosing method",
          any(h["id"] == "fn49" for h in hits), hits[:3])

    # the name-resolution caveat travels with the edges it qualifies
    edges = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "callers", "on").stdout)
    check("callers --json carries call_graph.resolution",
          edges["resolution"] == "name-based (approximate)", edges.get("resolution"))
    check("callers --json carries the caveat as text",
          "name" in (edges.get("warning") or ""), edges.get("warning"))


def test_xq_is_a_view_not_an_analysis():
    """The risk this pins: xq answering from its own derivation of the facts.

    A query tool that re-classified a role or recomputed an importance would
    disagree with xray.json, and the caller -- who used xq precisely to avoid
    reading xray.json -- would have no way to notice. So every functions[] entry
    xq serves must be the canonical object itself, and the same for the porting
    spec, the flows, the entry points and the summary.
    """
    print("xq matches xray.json exactly")
    if not os.path.isdir(SAMPLE_XRAYJS):
        check("sample .xrayjs present for fidelity test", False, SAMPLE_XRAYJS)
        return
    canon = json.load(open(os.path.join(SAMPLE_XRAYJS, "xray.json")))

    mismatched = []
    for fn in canon["functions"]:
        got = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "show", fn["id"]).stdout)
        if got["function"] != fn:
            mismatched.append(fn["id"])
    check("show --json returns every one of the %d functions[] entries unchanged"
          % len(canon["functions"]), not mismatched, mismatched[:5])

    by_name = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "show", "on").stdout)
    by_id = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "show", "fn197").stdout)
    check("name and id resolve to the same function",
          by_name["function"] == by_id["function"] and by_id["id"] == "fn197",
          by_name["id"])

    summary = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "summary").stdout)
    check("summary --json is the canonical summary",
          summary["summary"] == canon["summary"], summary["summary"])
    check("summary --json keeps the caveats verbatim",
          summary["confidence_notes"] == canon["confidence_notes"])

    entries = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "entries").stdout)
    check("entries --json is the canonical entry_points[]",
          entries["entry_points"] == canon["entry_points"])

    flow = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "flow", "fn49").stdout)
    check("flow --json extracts a flow without rewriting it",
          bool(flow["flows"]) and flow["flows"][0]["steps"] ==
          canon["flows"][flow["flows"][0]["index"]]["steps"],
          [f["index"] for f in flow["flows"]])

    port = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "port").stdout)
    for section in ("network_contracts", "inputs", "pitfalls"):
        check("port --json keeps %s verbatim" % section,
              port[section] == canon["porting"][section])
    # algorithms may gain python_snippets and nothing else: that snippet is a
    # lookup in report.PORT_SNIPPETS, not a fresh judgement about the algorithm
    for got, want in zip(port["algorithms"], canon["porting"]["algorithms"]):
        check("port --json leaves algorithm %s untouched" % want["id"],
              all(got[k] == want[k] for k in want),
              [k for k in want if got.get(k) != want[k]])
        check("port --json adds only python_snippets to %s" % want["id"],
              set(got) - set(want) == {"python_snippets"}, set(got) - set(want))

    # the snippet must be report.py's own, so report.md and xq cannot drift apart
    algo = canon["porting"]["algorithms"][0]
    family = algo["families"][0]
    # both findings the snippet depends on, or this compares against a snippet
    # for a different source than the one xq was asked about
    expected = report.port_snippet(family, algo["multiply_style"],
                                   algo.get("char_source"))
    served = json.loads(run_xq(SAMPLE_XRAYJS, "--json", "port", algo["id"]).stdout)
    snippets = {s["family"]: s["python"]
                for s in served["algorithms"][0]["python_snippets"]}
    check("port serves report.py snippets rather than a copy",
          snippets.get(family) == expected, snippets.get(family))

    # labels for functions xray.json does not detail come from the same
    # display_name that produced the published ones, so the two cannot diverge
    struct = json.load(open(os.path.join(SAMPLE_XRAYJS, "structure.json")))
    by_struct_id = explain.build_index(struct)
    published = {fn["id"]: fn["name"] for fn in canon["functions"]}
    for ep in canon["entry_points"]:
        published[ep["id"]] = ep["name"]
    drifted = [fid for fid, name in published.items()
               if fid in by_struct_id
               and explain.display_name(by_struct_id[fid], by_struct_id) != name]
    check("undetailed functions are named by the function that named the rest",
          not drifted, drifted[:5])


def test_xq_token_budget():
    """ACT-006: a narrow question must cost a fraction of reading xray.json.

    This is why the tool exists, so it is asserted rather than assumed. Ten times
    smaller is a floor, not the target -- the measured figures are well past it --
    but a floor catches the regression that matters: a subcommand quietly growing
    into a dump of the whole file.
    """
    print("xq token budget")
    if not os.path.isdir(SAMPLE_XRAYJS):
        check("sample .xrayjs present for budget test", False, SAMPLE_XRAYJS)
        return
    full = len(open(os.path.join(SAMPLE_XRAYJS, "xray.json")).read())

    for label, argv in (("show", ["show", "on"]),
                        ("find", ["find", "getConfig"]),
                        ("summary", ["summary"])):
        out = run_xq(SAMPLE_XRAYJS, *argv).stdout
        ratio = full / max(len(out), 1)
        check("%s costs 10x less than xray.json (%.0fx: %d vs %d chars)"
              % (label, ratio, len(out), full), ratio >= 10)

    # and one function answer stays well under the whole functions[] array, not
    # merely under the whole file
    canon = json.load(open(os.path.join(SAMPLE_XRAYJS, "xray.json")))
    all_fns = len(json.dumps(canon["functions"]))
    one = len(run_xq(SAMPLE_XRAYJS, "show", "on").stdout)
    check("show of one function is far smaller than all of functions[] (%d vs %d)"
          % (one, all_fns), one * 5 < all_fns)


def test_xq_fails_loudly():
    """Silence is the failure mode to avoid.

    An unknown schema, a missing artifact or an unresolvable name each have to say
    what is wrong -- and exit non-zero when the command cannot be answered at all.
    A caller that skipped xray.json has nothing else to notice the gap with.
    """
    print("xq failure modes")
    tmp = tempfile.mkdtemp(prefix="jsxray_xq_")
    try:
        # unknown schema: refuse, rather than answer from field names whose
        # meaning may have changed under them
        with open(os.path.join(tmp, "xray.json"), "w") as fh:
            json.dump({"schema": "js-xray/explanation/99", "summary": {}}, fh)
        proc = run_xq(tmp, "summary")
        check("unknown schema exits non-zero", proc.returncode != 0, proc.returncode)
        check("unknown schema names both schemas",
              "js-xray/explanation/99" in proc.stderr
              and "js-xray/explanation/1" in proc.stderr, proc.stderr[:200])

        empty = tempfile.mkdtemp(prefix="jsxray_xq_empty_")
        proc = run_xq(empty, "summary")
        check("missing xray.json exits non-zero", proc.returncode != 0, proc.returncode)
        check("missing xray.json is named", "xray.json" in proc.stderr,
              proc.stderr[:200])
        shutil.rmtree(empty, ignore_errors=True)

        # a real xray.json with no structure.json: callers cannot be answered, and
        # the error names the artifact instead of returning an empty list
        partial = tempfile.mkdtemp(prefix="jsxray_xq_partial_")
        shutil.copy(os.path.join(SAMPLE_XRAYJS, "xray.json"), partial)
        proc = run_xq(partial, "callers", "on")
        check("callers without structure.json exits non-zero",
              proc.returncode != 0, proc.returncode)
        check("callers without structure.json names it",
              "structure.json" in proc.stderr, proc.stderr[:200])
        proc = run_xq(partial, "grep", "fetch")
        check("grep without clean.js names it",
              proc.returncode != 0 and "clean.js" in proc.stderr, proc.stderr[:200])
        # a question that needs neither still answers
        proc = run_xq(partial, "show", "on")
        check("show still answers from xray.json alone",
              proc.returncode == 0 and "network transport" in proc.stdout,
              proc.stdout[:200])
        check("show says the source is unavailable rather than omitting it",
              "clean.js missing" in proc.stdout, proc.stdout[-200:])
        shutil.rmtree(partial, ignore_errors=True)

        proc = run_xq(SAMPLE_XRAYJS, "show", "nosuchfunction")
        check("unknown name is reported", "no function matches" in proc.stdout,
              proc.stdout[:200])
        check("unknown name suggests find", "find" in proc.stdout, proc.stdout[:200])

        proc = run_xq(os.path.join(tmp, "nope"), "summary")
        check("missing directory exits non-zero", proc.returncode != 0, proc.returncode)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_xq_warns_on_vm_obfuscated():
    """A caller querying a VM-obfuscated file must be told before reading the answer.

    xq is what makes reading xray.json optional, which also means the caller never
    sees summary.vm_obfuscation unless xq shows it. Without the banner, "what does
    fn0 do" gets a truthful answer about an interpreter part, and the caller
    reports it as the module behaviour.
    """
    print("xq vm warning")
    fixture = os.path.join(ROOT, "fixtures", "vmp_interpreter.js")
    if not os.path.isfile(fixture):
        check("vmp fixture present for xq", False, fixture)
        return
    outdir = tempfile.mkdtemp(prefix="jsxray_xq_vm_")
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "xray.py"), fixture, "-o", outdir],
            capture_output=True, text=True)
        check("vm pipeline ran for xq", proc.returncode == 0, proc.stderr[-300:])
        data = json.load(open(os.path.join(outdir, "xray.json")))
        check("fixture is the vm-obfuscated case",
              data["summary"].get("vm_obfuscation") == "vm-obfuscated",
              data["summary"].get("vm_obfuscation"))

        for label, argv in (("show", ["show", "fn0"]), ("port", ["port"]),
                            ("summary", ["summary"])):
            out = run_xq(outdir, *argv).stdout
            check("xq %s warns about the VM" % label, "VM-obfuscated" in out, out[:160])
            # first line, not a footnote: a warning after the answer is one the
            # caller has already acted on
            check("xq %s warns before it answers" % label,
                  out.lstrip().startswith("!"), out[:80])

        flow_out = run_xq(outdir, "flow", "fn0").stdout
        check("xq flow warns about the VM", "VM-obfuscated" in flow_out, flow_out[:160])
        check("xq --json exposes the verdict for a caller that parses",
              json.loads(run_xq(outdir, "--json", "show", "fn0").stdout)
              .get("vm_obfuscation") == "vm-obfuscated")

        # and a file that is not VM-obfuscated must not pick up a banner
        clean_out = run_xq(SAMPLE_XRAYJS, "show", "on").stdout
        check("no VM banner on a file that is not VM-obfuscated",
              "VM-obfuscated" not in clean_out
              and not clean_out.lstrip().startswith("!"), clean_out[:120])
    finally:
        shutil.rmtree(outdir, ignore_errors=True)



def test_xq_resolves_its_target():
    """The path may be left out, but never guessed at.

    Typing the .xrayjs path on every question is what the tool exists to avoid, so
    the first argument is optional -- and that only pays off if a caller can trust
    which run answered. The ambiguous case is the one that matters: two runs in a
    directory must produce a refusal, not the alphabetically first answer, because
    a correct answer about the wrong file reads exactly like a correct answer.
    """
    print("xq target resolution")
    if not os.path.isdir(SAMPLE_XRAYJS):
        check("sample .xrayjs present for resolution", False, SAMPLE_XRAYJS)
        return

    # backward compatibility: an explicit directory still works, and is not
    # announced back. The one stderr line it may carry is which explanation
    # artifact answered (xray.toon or xray.json), which the caller never named.
    proc = run_xq(SAMPLE_XRAYJS, "summary")
    check("explicit directory still answers",
          proc.returncode == 0 and "functions 220" in proc.stdout, proc.stdout[:120])
    check("explicit directory is not announced back",
          all(line.startswith("xq: read ") for line in proc.stderr.splitlines()),
          proc.stderr[:120])

    tmp = tempfile.mkdtemp(prefix="jsxray_target_")
    try:
        # one run, reached from the cwd with no path at all
        solo = os.path.join(tmp, "solo")
        os.makedirs(solo)
        shutil.copytree(SAMPLE_XRAYJS, os.path.join(solo, "sentinel_sdk.xrayjs"))
        proc = run_xq_in(solo, "summary")
        check("subcommand alone resolves the only run in the cwd",
              proc.returncode == 0 and "functions 220" in proc.stdout,
              (proc.stdout[:120], proc.stderr[:120]))
        check("the chosen run is named on stderr",
              "sentinel_sdk.xrayjs" in proc.stderr, proc.stderr[:120])
        check("stdout carries the answer only, so parsing still works",
              "sentinel_sdk.xrayjs" not in proc.stdout.split("\n")[0],
              proc.stdout[:120])

        # --json must not gain a line either: the notice belongs on stderr
        proc = run_xq_in(solo, "--json", "summary")
        check("--json output stays valid JSON when the target was inferred",
              json.loads(proc.stdout).get("summary", {}).get("functions") == 220,
              proc.stdout[:120])
        check("--json announces the run on stderr", "sentinel_sdk.xrayjs" in proc.stderr,
              proc.stderr[:120])

        # a .js path resolves to the run beside it
        open(os.path.join(solo, "sentinel_sdk.js"), "w").close()
        proc = run_xq_in(solo, "sentinel_sdk.js", "show", "on")
        check("a .js path finds its paired .xrayjs",
              proc.returncode == 0 and "fn197" in proc.stdout,
              (proc.stdout[:120], proc.stderr[:120]))
        check("the pairing is stated", "paired with sentinel_sdk.js" in proc.stderr,
              proc.stderr[:120])

        # an unanalysed .js is a different failure from a missing file, and says so
        open(os.path.join(solo, "unrun.js"), "w").close()
        proc = run_xq_in(solo, "unrun.js", "summary")
        check("an unanalysed .js exits non-zero", proc.returncode != 0, proc.returncode)
        check("an unanalysed .js says it was never analysed",
              "has not been analysed" in proc.stderr and "unrun.xrayjs" in proc.stderr,
              proc.stderr[:200])
        check("an unanalysed .js points at the pipeline",
              "xray.py" in proc.stderr, proc.stderr[:200])

        # the case this exists for: two runs, no path, no guess
        pair = os.path.join(tmp, "pair")
        os.makedirs(pair)
        for name in ("alpha.xrayjs", "beta.xrayjs"):
            shutil.copytree(SAMPLE_XRAYJS, os.path.join(pair, name))
        proc = run_xq_in(pair, "summary")
        check("two candidates exit non-zero", proc.returncode != 0, proc.returncode)
        check("two candidates are both listed",
              "alpha.xrayjs" in proc.stderr and "beta.xrayjs" in proc.stderr,
              proc.stderr[:200])
        check("an ambiguous target answers nothing at all", proc.stdout == "",
              proc.stdout[:200])
        # and naming one resolves it
        proc = run_xq_in(pair, "beta.xrayjs", "summary")
        check("naming one of the candidates answers",
              proc.returncode == 0 and "functions 220" in proc.stdout, proc.stdout[:120])

        # no runs at all: say so, rather than reporting an empty analysis
        bare = os.path.join(tmp, "bare")
        os.makedirs(bare)
        proc = run_xq_in(bare, "summary")
        check("no run in the cwd exits non-zero", proc.returncode != 0, proc.returncode)
        check("no run in the cwd says which directory it looked in",
              ".xrayjs" in proc.stderr and bare in proc.stderr, proc.stderr[:200])

        # the search is one level deep: a run nested below the cwd is not reached,
        # so the cost of "xq summary" does not depend on the size of the tree
        nested = os.path.join(tmp, "nested")
        os.makedirs(os.path.join(nested, "deep"))
        shutil.copytree(SAMPLE_XRAYJS, os.path.join(nested, "deep", "buried.xrayjs"))
        proc = run_xq_in(nested, "summary")
        check("the cwd search does not recurse", proc.returncode != 0
              and "buried" not in proc.stdout, (proc.returncode, proc.stdout[:120]))

        # a run directory -o named something else is still a run. Recognising it
        # by name meant "-o popup.xrayout" was invisible to the cwd search and the
        # caller went back to typing full paths.
        renamed = os.path.join(tmp, "renamed")
        os.makedirs(renamed)
        shutil.copytree(SAMPLE_XRAYJS, os.path.join(renamed, "popup.xrayout"))
        proc = run_xq_in(renamed, "summary")
        check("a run directory not named .xrayjs resolves from the cwd",
              proc.returncode == 0 and "functions 220" in proc.stdout,
              (proc.returncode, proc.stdout[:120], proc.stderr[:200]))
        check("the differently-named run is the one announced",
              "popup.xrayout" in proc.stderr, proc.stderr[:200])

        # the safety this widening makes more important, not less: broadening what
        # counts as a candidate can only produce more candidates, and two of them
        # must still be a refusal rather than a guess
        mixed = os.path.join(tmp, "mixed")
        os.makedirs(mixed)
        shutil.copytree(SAMPLE_XRAYJS, os.path.join(mixed, "popup.xrayout"))
        shutil.copytree(SAMPLE_XRAYJS, os.path.join(mixed, "other.xrayjs"))
        proc = run_xq_in(mixed, "summary")
        check("two candidates of different names still exit 3",
              proc.returncode == 3, proc.returncode)
        check("both differently-named candidates are listed",
              "popup.xrayout" in proc.stderr and "other.xrayjs" in proc.stderr,
              proc.stderr[:200])
        check("the widened search still answers nothing when ambiguous",
              proc.stdout == "", proc.stdout[:200])
        proc = run_xq_in(mixed, "popup.xrayout", "summary")
        check("naming the -o directory resolves the ambiguity",
              proc.returncode == 0 and "functions 220" in proc.stdout, proc.stdout[:120])

        # two run directories that share nothing but their contents: the rule is
        # "holds an explanation artifact", so neither name matters
        pairless = os.path.join(tmp, "pairless")
        os.makedirs(pairless)
        for name in ("out1", "out2"):
            shutil.copytree(SAMPLE_XRAYJS, os.path.join(pairless, name))
        proc = run_xq_in(pairless, "summary")
        check("suffix-less candidates are found and still refused",
              proc.returncode == 3 and "out1" in proc.stderr and "out2" in proc.stderr,
              (proc.returncode, proc.stderr[:200]))

        # ...and an ordinary directory that holds no explanation is not a candidate,
        # so a source tree beside one run does not turn into an ambiguity
        oneplus = os.path.join(tmp, "oneplus")
        os.makedirs(os.path.join(oneplus, "src"))
        os.makedirs(os.path.join(oneplus, "node_modules"))
        shutil.copytree(SAMPLE_XRAYJS, os.path.join(oneplus, "only.xrayout"))
        proc = run_xq_in(oneplus, "summary")
        check("directories without an explanation are not candidates",
              proc.returncode == 0 and "only.xrayout" in proc.stderr,
              (proc.returncode, proc.stderr[:200]))

        # a directory named after a subcommand: the path wins, and when that leaves
        # no command to run, the collision is explained rather than reported as a
        # missing argument
        clash = os.path.join(tmp, "clash")
        os.makedirs(clash)
        shutil.copytree(SAMPLE_XRAYJS, os.path.join(clash, "summary"))
        proc = run_xq_in(clash, "summary", "show", "on")
        check("a run directory named like a subcommand is usable as a path",
              proc.returncode == 0 and "fn197" in proc.stdout,
              (proc.stdout[:120], proc.stderr[:200]))
        proc = run_xq_in(clash, "summary")
        check("the subcommand/path collision is explained",
              proc.returncode != 0 and "both a subcommand and a run directory"
              in proc.stderr, proc.stderr[:200])

        # ...but an ordinary directory of that name must not shadow the subcommand
        plain = os.path.join(tmp, "plain")
        os.makedirs(os.path.join(plain, "port"))
        shutil.copytree(SAMPLE_XRAYJS, os.path.join(plain, "only.xrayjs"))
        proc = run_xq_in(plain, "port")
        check("a non-run directory does not shadow a subcommand",
              proc.returncode == 0 and "only.xrayjs" in proc.stderr
              and "FNV-1a" in proc.stdout,
              (proc.returncode, proc.stdout[:160], proc.stderr[:160]))

        # a suggested follow-up command has to be runnable as written, which means
        # echoing the form the caller used instead of the resolved path -- printing
        # the long path teaches back the typing the resolution exists to remove
        proc = run_xq_in(plain, "show", "nosuchfunction")
        check("the retry hint keeps the short form when no path was given",
              "Try: xq find nosuchfunction" in proc.stdout, proc.stdout[:200])
        proc = run_xq_in(solo, "sentinel_sdk.js", "show", "nosuchfunction")
        check("the retry hint echoes the .js path the caller used",
              "Try: xq sentinel_sdk.js find" in proc.stdout, proc.stdout[:200])
        proc = run_xq(SAMPLE_XRAYJS, "show", "nosuchfunction")
        check("the retry hint still names an explicit directory",
              ("Try: xq %s find" % SAMPLE_XRAYJS) in proc.stdout, proc.stdout[:200])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


INSTALLER = os.path.join(ROOT, "scripts", "install-xq.sh")


def test_install_xq_script():
    """The installer is tested against a throwaway bin directory, never the user's.

    Every invocation here passes --bin-dir into a mkdtemp, which is the only
    reason a test suite may exercise an installer at all: a test that linked into
    ~/.local/bin would rewrite the developer's own environment as a side effect of
    running the suite. The dry run is checked for writing nothing, and the real
    run for being safe to repeat.
    """
    print("install-xq")
    if not os.path.isfile(INSTALLER):
        check("installer present", False, INSTALLER)
        return
    source = os.path.join(SCRIPTS, "xq.py")
    check("xq.py is executable, as the installer relies on",
          os.access(source, os.X_OK), source)

    tmp = tempfile.mkdtemp(prefix="jsxray_install_")

    def install(bin_dir, *extra):
        return subprocess.run(["sh", INSTALLER, "--bin-dir", bin_dir] + list(extra),
                              capture_output=True, text=True, cwd=tmp)

    try:
        # --dry-run reports the link and creates nothing
        dry = os.path.join(tmp, "dry")
        proc = install(dry, "--dry-run")
        check("dry run succeeds", proc.returncode == 0, proc.stderr[-200:])
        check("dry run says what it would link",
              "would link" in proc.stdout and "xq.py" in proc.stdout,
              proc.stdout[-300:])
        check("dry run writes nothing", not os.path.exists(dry), dry)

        # the real thing links, and the link resolves to this checkout
        live = os.path.join(tmp, "live")
        proc = install(live)
        link = os.path.join(live, "xq")
        check("install succeeds", proc.returncode == 0, proc.stderr[-200:])
        check("install creates a symlink", os.path.islink(link), link)
        check("the link points at this checkout",
              os.path.realpath(link) == os.path.realpath(source),
              os.path.realpath(link))

        # idempotent: a second run is a no-op, not an error and not a duplicate
        proc = install(live)
        check("a second install is a no-op", proc.returncode == 0
              and "nothing to do" in proc.stdout, proc.stdout[-200:])
        check("the link survives the second run",
              os.path.realpath(link) == os.path.realpath(source),
              os.path.realpath(link))

        # a directory not on the PATH is called out, since the command would
        # otherwise appear installed and still not run
        check("an off-PATH target is a warning", "not on your PATH" in proc.stdout,
              proc.stdout[-200:])
        check("the warning says how to fix it", "PATH=" in proc.stdout,
              proc.stdout[-200:])

        # someone else's xq is left exactly as it was
        foreign_dir = os.path.join(tmp, "foreign")
        os.makedirs(foreign_dir)
        foreign = os.path.join(foreign_dir, "xq")
        os.symlink("/bin/echo", foreign)
        proc = install(foreign_dir)
        check("a foreign xq is not replaced", proc.returncode != 0, proc.returncode)
        check("a foreign xq is still itself afterwards",
              os.readlink(foreign) == "/bin/echo", os.readlink(foreign))
        check("refusing to replace it is explained",
              "Refusing to replace" in proc.stderr, proc.stderr[-200:])

        # nor is a real file of that name
        file_dir = os.path.join(tmp, "regular")
        os.makedirs(file_dir)
        with open(os.path.join(file_dir, "xq"), "w") as fh:
            fh.write("#!/bin/sh\necho not ours\n")
        proc = install(file_dir)
        check("a regular file named xq is not replaced",
              proc.returncode != 0 and "not a symlink" in proc.stderr,
              proc.stderr[-200:])

        # a stale link from another checkout of this same tool is ours to update
        stale_dir = os.path.join(tmp, "stale")
        old = os.path.join(tmp, "old", "skill", "scripts")
        os.makedirs(stale_dir)
        os.makedirs(old)
        open(os.path.join(old, "xq.py"), "w").close()
        os.symlink(os.path.join(old, "xq.py"), os.path.join(stale_dir, "xq"))
        proc = install(stale_dir)
        check("a stale js-xray link is repointed", proc.returncode == 0
              and "repoint" in proc.stdout, (proc.returncode, proc.stdout[-200:]))
        check("the repointed link is current",
              os.path.realpath(os.path.join(stale_dir, "xq"))
              == os.path.realpath(source),
              os.path.realpath(os.path.join(stale_dir, "xq")))

        # and the installed command actually answers through the link
        run = os.path.join(tmp, "run")
        install(run)
        if os.path.isdir(SAMPLE_XRAYJS):
            env = dict(os.environ, PATH=run + os.pathsep + os.environ.get("PATH", ""))
            proc = subprocess.run(["xq", SAMPLE_XRAYJS, "summary"],
                                  capture_output=True, text=True, env=env)
            check("the installed xq answers as a bare command",
                  proc.returncode == 0 and "functions 220" in proc.stdout,
                  (proc.returncode, proc.stdout[:120], proc.stderr[:200]))

        # nothing above went near the real user bin directory
        real = os.path.join(os.path.expanduser("~"), ".local", "bin", "xq")
        before = os.path.realpath(real) if os.path.lexists(real) else None
        check("the suite never wrote to ~/.local/bin",
              before is None or before == os.path.realpath(source), before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# xq reads xray.toon or xray.json interchangeably
# ---------------------------------------------------------------------------

# Every subcommand, in the shape the CLI takes them. Both text and --json are
# compared, because they are produced by different branches of each command: a
# decode bug could leave the human output identical and shift a --json field.
XQ_EQUIVALENCE_ARGV = [
    ["summary"],
    ["find", "getConfig"],
    ["find", "^on$"],
    ["find", "sentinel", "--strings"],
    ["show", "on"],
    ["show", "fn49"],
    ["show", "fn197", "--full"],
    ["callers", "on"],
    ["callers", "fn195", "--depth", "2"],
    ["callees", "on"],
    ["flow", "fn49"],
    ["port"],
    ["port", "FNV"],
    ["grep", "fetch"],
    ["grep", "Math.imul"],
    ["entries"],
    ["entries", "--traced"],
    ["roles"],
    ["roles", "hash"],
]


def test_xq_reads_toon_and_json_identically():
    """The same question must get the same answer whichever artifact was read.

    xray.toon is xray.json re-encoded, so every xq answer has to be
    byte-identical between the two. Comparing outputs is the only check that
    covers the whole path: a decoder bug that drops one tabular row or shifts
    one field would leave the TOON decode succeeding and quietly change an
    answer, and no assertion about the decoder in isolation would catch what
    reached the caller.

    Each format gets its own copy of the run with the *other* artifact removed,
    so neither run can fall back to the file under test and pass by accident.
    """
    print("xq reads xray.toon and xray.json identically")
    if not os.path.isdir(SAMPLE_XRAYJS):
        check("sample .xrayjs present for toon/json equivalence", False, SAMPLE_XRAYJS)
        return

    tmp = tempfile.mkdtemp(prefix="jsxray_toon_eq_")
    try:
        toon_dir = os.path.join(tmp, "toon_only.xrayjs")
        json_dir = os.path.join(tmp, "json_only.xrayjs")
        shutil.copytree(SAMPLE_XRAYJS, toon_dir)
        shutil.copytree(SAMPLE_XRAYJS, json_dir)

        source_toon = os.path.join(SAMPLE_XRAYJS, "xray.toon")
        if not os.path.isfile(source_toon):
            # The sample ships xray.toon; if it ever stops shipping one, encode
            # it here rather than skipping -- a skipped equivalence test looks
            # exactly like a passing one in the summary line.
            sys.path.insert(0, SCRIPTS)
            import toon_encoder  # noqa: PLC0415 -- only needed on this path
            with open(os.path.join(SAMPLE_XRAYJS, "xray.json"), encoding="utf-8") as fh:
                value = json.load(fh)
            for target in (toon_dir, json_dir):
                with open(os.path.join(target, "xray.toon"), "w",
                          encoding="utf-8", newline="\n") as fh:
                    fh.write(toon_encoder.encode(value))
        os.remove(os.path.join(toon_dir, "xray.json"))
        os.remove(os.path.join(json_dir, "xray.toon"))

        check("the toon-only copy really has no xray.json",
              not os.path.exists(os.path.join(toon_dir, "xray.json")), toon_dir)
        check("the json-only copy really has no xray.toon",
              not os.path.exists(os.path.join(json_dir, "xray.toon")), json_dir)

        differing = []
        for argv in XQ_EQUIVALENCE_ARGV:
            label = " ".join(argv)
            for flags in ([], ["--json"]):
                from_toon = run_xq(toon_dir, *(flags + argv))
                from_json = run_xq(json_dir, *(flags + argv))
                shown = label + (" --json" if flags else "")
                if from_toon.returncode != from_json.returncode:
                    differing.append("%s: exit %d vs %d"
                                     % (shown, from_toon.returncode, from_json.returncode))
                    continue
                if from_toon.stdout != from_json.stdout:
                    differing.append("%s: stdout differs" % shown)
        check("every subcommand answers identically from either artifact",
              not differing, "; ".join(differing[:6]))

        # and the provenance line says which one it read, on stderr only
        proc = run_xq(toon_dir, "summary")
        check("reading TOON is reported on stderr",
              "read xray.toon" in proc.stderr, proc.stderr[:160])
        check("the provenance note stays off stdout",
              "xray.toon" not in proc.stdout, proc.stdout[:160])
        proc = run_xq(json_dir, "summary")
        check("falling back to JSON is reported on stderr",
              "read xray.json" in proc.stderr, proc.stderr[:160])
        check("--json output carries no provenance line",
              run_xq(toon_dir, "--json", "summary").stderr == "",
              run_xq(toon_dir, "--json", "summary").stderr[:160])

        # TOON wins when both are present, and the answer is the same either way
        both = os.path.join(tmp, "both.xrayjs")
        shutil.copytree(SAMPLE_XRAYJS, both)
        proc = run_xq(both, "summary")
        check("xray.toon is preferred when both are present",
              "read xray.toon" in proc.stderr, proc.stderr[:160])
        check("the answer is the same as the json-only copy",
              proc.stdout == run_xq(json_dir, "summary").stdout, "")

        # a corrupt xray.toon is reported, not silently replaced by xray.json:
        # the two are meant to agree, and one that no longer parses means they
        # may not, which the caller has to hear about
        broken = os.path.join(tmp, "broken.xrayjs")
        shutil.copytree(SAMPLE_XRAYJS, broken)
        with open(os.path.join(broken, "xray.toon"), encoding="utf-8") as fh:
            text = fh.read()
        lines = text.split("\n")
        for i, line in enumerate(lines):
            # a tabular header: drop one of its rows so the count no longer matches
            if "]{" in line and line.rstrip().endswith(":"):
                del lines[i + 1]
                break
        else:
            check("the sample's xray.toon has a tabular header to corrupt", False, "")
        with open(os.path.join(broken, "xray.toon"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines))
        proc = run_xq(broken, "summary")
        check("a corrupt xray.toon exits non-zero", proc.returncode != 0,
              (proc.returncode, proc.stdout[:120]))
        check("a corrupt xray.toon is named, with the line",
              "xray.toon" in proc.stderr and "line" in proc.stderr, proc.stderr[:200])
        check("a corrupt xray.toon does not quietly answer from xray.json",
              "functions 220" not in proc.stdout, proc.stdout[:160])

        # neither artifact: the failure names both, instead of only the one that
        # used to be the single source
        empty = os.path.join(tmp, "empty.xrayjs")
        os.makedirs(empty)
        proc = run_xq(empty, "summary")
        check("a run with neither artifact exits non-zero", proc.returncode != 0,
              proc.returncode)
        check("the failure names both artifacts",
              "xray.toon" in proc.stderr and "xray.json" in proc.stderr,
              proc.stderr[:200])

        # the schema gate applies to the TOON path too: an unknown schema must be
        # refused whichever encoding carried it
        stale = os.path.join(tmp, "stale.xrayjs")
        os.makedirs(stale)
        sys.path.insert(0, SCRIPTS)
        import toon_encoder as _toon  # noqa: PLC0415 -- test-local
        with open(os.path.join(stale, "xray.toon"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(_toon.encode({"schema": "js-xray/explanation/99", "summary": {}}))
        proc = run_xq(stale, "summary")
        check("an unknown schema in TOON exits non-zero", proc.returncode != 0,
              proc.returncode)
        check("an unknown schema in TOON names both schemas and the file",
              "js-xray/explanation/99" in proc.stderr
              and "js-xray/explanation/1" in proc.stderr
              and "xray.toon" in proc.stderr, proc.stderr[:250])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_brace_matching()
    test_keyword_not_function()
    test_class_field_arrow_named()
    test_anonymous_block_qualified()
    test_line_numbers()
    test_scoped_string_arrays()
    test_inline_syntax_gate()
    test_deflatten_execution_equivalence()
    test_deflatten_leaves_undecidable_alone()
    test_deflatten_rollback()
    test_deflatten_stage_in_pipeline()
    test_wrapper_inlining_execution_equivalence()
    test_wrapper_inlining_refuses_lookalikes()
    test_wrapper_inlining_improves_classification()
    test_deflatten_regression_on_existing_fixtures()
    test_pipeline_end_to_end()
    test_deobfuscation_reports_both_passes()
    test_truncated_functions_are_visible()
    test_default_outdir_naming()
    test_custom_anchors()
    test_graceful_on_plain_file()
    test_multiply_style()
    test_astral_char_encoding()
    test_endpoint_and_storage_recovery()
    test_reachability_ignores_flow_budget()
    test_pipeline_log_records_failure()
    test_toon_stage()
    test_vm_detection_positive()
    test_vm_detection_no_false_positives()
    test_vm_warning_reaches_outputs()
    test_anti_analysis_positive()
    test_anti_analysis_no_false_positives()
    test_anti_analysis_requires_more_than_one_behaviour()
    test_anti_analysis_role_is_not_inherited()
    test_anti_analysis_improves_the_histogram()
    test_xq_subcommands()
    test_xq_is_a_view_not_an_analysis()
    test_xq_token_budget()
    test_xq_fails_loudly()
    test_xq_warns_on_vm_obfuscated()
    test_xq_resolves_its_target()
    test_xq_reads_toon_and_json_identically()
    test_install_xq_script()
    print("")
    print("passed %d, failed %d" % (len(PASS), len(FAIL)))
    for name, detail in FAIL:
        print("  FAILED: %s %s" % (name, detail))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
