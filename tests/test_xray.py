#!/usr/bin/env python3
"""Test suite for js-xray. Run: python3 tests/test_xray.py"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skill", "scripts")
sys.path.insert(0, SCRIPTS)

import analyze  # noqa: E402

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
        check("report has porting guide", "Python porting guide" in rep)
        check("report has code fence", (BT * 3 + "javascript") in rep)
        check("report shows FNV hint", "16777619" in rep)


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


def main():
    test_brace_matching()
    test_keyword_not_function()
    test_line_numbers()
    test_pipeline_end_to_end()
    test_custom_anchors()
    test_graceful_on_plain_file()
    print("")
    print("passed %d, failed %d" % (len(PASS), len(FAIL)))
    for name, detail in FAIL:
        print("  FAILED: %s %s" % (name, detail))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
