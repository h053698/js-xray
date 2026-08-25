#!/usr/bin/env python3
"""Tests for skill/scripts/toon_encoder.py. Run: python3 skill/tests/test_toon_encoder.py

Covers:
  - The four TOON v4.1 forms (inline, list, tabular, keyed tabular) against
    the spec's own Appendix A examples.
  - Edge cases: quoting (comma/newline/quote/colon), empty arrays, null,
    non-uniform object arrays falling back to list form.
  - Round-trip verification: encode with this module, decode with the
    reference @toon-format/toon (npm, v4.1.1) via a small Node CLI shim, and
    compare the decoded value against the original JSON for structural
    equality. If Node or the npm reference package is unavailable, the
    round-trip check is skipped with a clear message rather than silently
    passing (there is no bundled fallback TOON decoder in this repo).
"""
import json
import math
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "skill", "scripts")
sys.path.insert(0, SCRIPTS)

import toon_encoder as toon  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print("  ok   %s" % name)
    else:
        FAIL.append((name, detail))
        print("  FAIL %s %s" % (name, detail))


def check_eq(name, got, want):
    check(name, got == want, "got=%r want=%r" % (got, want))


# ---------------------------------------------------------------------------
# Four forms, against the spec's Appendix A examples
# ---------------------------------------------------------------------------

def test_inline_form():
    print("inline form (SPEC S9.1)")
    check_eq("primitive array", toon.encode({"tags": ["admin", "ops", "dev"]}),
              "tags[3]: admin,ops,dev")
    check_eq("empty array", toon.encode({"tags": []}), "tags: []")
    check_eq("root empty array", toon.encode([]), "[]")
    check_eq("root primitive array", toon.encode([1, 2, 3]), "[3]: 1,2,3")


def test_list_form():
    print("list form (SPEC S9.2, S9.4)")
    check_eq("array of primitive arrays", toon.encode({"pairs": [[1, 2], [3, 4]]}),
              "pairs[2]:\n  - [2]: 1,2\n  - [2]: 3,4")
    check_eq("mixed array", toon.encode({"items": [1, {"a": 1}, "text"]}),
              "items[3]:\n  - 1\n  - a: 1\n  - text")
    check_eq("objects as list items", toon.encode({"items": [
        {"id": 1, "name": "First"},
        {"id": 2, "name": "Second", "extra": True},
    ]}), "items[2]:\n  - id: 1\n    name: First\n  - id: 2\n    name: Second\n    extra: true")


def test_tabular_form():
    print("tabular form (SPEC S9.3)")
    check_eq("uniform object array", toon.encode({"items": [
        {"sku": "A1", "qty": 2, "price": 9.99},
        {"sku": "B2", "qty": 1, "price": 14.5},
    ]}), "items[2]{sku,qty,price}:\n  A1,2,9.99\n  B2,1,14.5")
    check_eq("nested field group", toon.encode({"orders": [
        {"id": 1, "customer": {"name": "Ada", "country": "DK"}, "total": 99},
        {"id": 2, "customer": {"name": "Bob", "country": "UK"}, "total": 149},
    ]}), "orders[2]{id,customer{name,country},total}:\n  1,Ada,DK,99\n  2,Bob,UK,149")


def test_keyed_tabular_form():
    print("keyed tabular form (SPEC S9.5)")
    check_eq("object of uniform objects", toon.encode({"users": {
        "alice": {"age": 30, "city": "Berlin"},
        "bob": {"age": 25, "city": "Oslo"},
    }}), "users[2:]{age,city}:\n  alice: 30,Berlin\n  bob: 25,Oslo")
    check_eq("single entry does not qualify (SPEC S9.5: >=2 entries)",
              toon.encode({"users": {"alice": {"age": 30, "city": "Berlin"}}}),
              "users:\n  alice:\n    age: 30\n    city: Berlin")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_quoting_edge_cases():
    print("quoting edge cases (SPEC S7.1, S7.2)")
    check_eq("comma in string", toon.encode({"note": "a,b"}), 'note: "a,b"')
    check_eq("newline in string", toon.encode({"note": "a\nb"}), 'note: "a\\nb"')
    check_eq("quote in string", toon.encode({"note": 'a"b'}), 'note: "a\\"b"')
    check_eq("colon in string", toon.encode({"note": "a:b"}), 'note: "a:b"')
    check_eq("backslash in string", toon.encode({"note": "a\\b"}), 'note: "a\\\\b"')
    check_eq("leading hyphen", toon.encode({"note": "-x"}), 'note: "-x"')
    check_eq("leading hash", toon.encode({"note": "#tag"}), 'note: "#tag"')
    check_eq("looks like number", toon.encode({"note": "42"}), 'note: "42"')
    check_eq("looks like bool", toon.encode({"note": "true"}), 'note: "true"')
    check_eq("leading/trailing space", toon.encode({"note": " x "}), 'note: " x "')
    check_eq("brackets", toon.encode({"note": "a[b]"}), 'note: "a[b]"')
    check_eq("null value", toon.encode({"note": None}), "note: null")
    check_eq("quoted key", toon.encode({"my-key": 1}), '"my-key": 1')
    check_eq("comma inside tabular cell", toon.encode({"items": [
        {"a": "x,y"}, {"a": "p,q"},
    ]}), 'items[2]{a}:\n  "x,y"\n  "p,q"')
    check_eq("tab character escaped", toon.encode({"note": "a\tb"}), 'note: "a\\tb"')
    check_eq("control char escaped", toon.encode({"note": "a\x01b"}), 'note: "a\\u0001b"')


def test_nonuniform_falls_back_to_list():
    print("non-uniform object arrays fall back to list form (SPEC S9.3)")
    # different key sets -> not tabular
    got = toon.encode({"items": [{"a": 1, "b": 2}, {"a": 1, "c": 3}]})
    check("different key sets -> list form", got.startswith("items[2]:\n  - "), got)
    check("no field-list header for non-uniform array", "{a,b}" not in got and "{a,c}" not in got, got)

    # one element is an empty object -> not tabular even though shapes could
    # otherwise "match" (SPEC S9.3: any empty object disqualifies tabular form)
    got2 = toon.encode({"items": [{}, {"a": 1}]})
    check("empty object disqualifies tabular", "items[2]:" in got2 and "{a}" not in got2, got2)

    # a column mixing a primitive and an object is not uniform-primitive nor
    # nested-uniform -> disqualifies the whole array
    got3 = toon.encode({"items": [{"a": 1}, {"a": {"x": 1}}]})
    check("mixed-type column disqualifies tabular", "items[2]:" in got3 and "{a}" not in got3, got3)


def test_number_formatting():
    print("number canonical form (SPEC S2)")
    check_eq("negative zero", toon.encode({"n": -0.0}), "n: 0")
    check_eq("trailing zero float", toon.encode({"n": 1.50}), "n: 1.5")
    check_eq("integer-valued float", toon.encode({"n": 2.0}), "n: 2")
    check_eq("small decimal", toon.encode({"n": 0.000001}), "n: 0.000001")
    check_eq("nan to null", toon.encode({"n": float("nan")}), "n: null")
    check_eq("inf to null", toon.encode({"n": float("inf")}), "n: null")
    check_eq("neg inf to null", toon.encode({"n": float("-inf")}), "n: null")
    check_eq("bool not number", toon.encode({"n": True}), "n: true")


def test_empty_object_and_root():
    print("empty object / root forms (SPEC S8)")
    check_eq("empty object field", toon.encode({"obj": {}}), "obj:")
    check_eq("empty root object", toon.encode({}), "")
    check_eq("single primitive root", toon.encode("hello"), "hello")
    check_eq("single number root", toon.encode(42), "42")


# ---------------------------------------------------------------------------
# Round-trip verification against the reference decoder
# ---------------------------------------------------------------------------

def _find_node():
    node = shutil.which("node")
    return node


def _reference_decode(node, decode_cli, toon_text):
    proc = subprocess.run([node, decode_cli], input=toon_text, capture_output=True, text=True)
    if proc.returncode != 0:
        return None, proc.stderr
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, "bad JSON from reference decoder: %s (stdout=%r)" % (exc, proc.stdout[:400])


def _json_equal(a, b):
    """JSON-model equality per SPEC S2: -0 == 0, ints == floats with same value."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, dict) and isinstance(b, dict):
        if list(a.keys()) != list(b.keys()):
            return False
        return all(_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_json_equal(x, y) for x, y in zip(a, b))
    return a == b


ROUND_TRIP_CASES = [
    ("simple object", {"id": 123, "name": "Ada", "active": True, "score": None}),
    ("nested object", {"user": {"id": 1, "profile": {"bio": "hi there"}}}),
    ("tabular array", {"items": [
        {"sku": "A1", "qty": 2, "price": 9.99},
        {"sku": "B2", "qty": 1, "price": 14.5},
    ]}),
    ("nested field group", {"orders": [
        {"id": 1, "customer": {"name": "Ada", "country": "DK"}, "total": 99},
        {"id": 2, "customer": {"name": "Bob", "country": "UK"}, "total": 149},
    ]}),
    ("keyed tabular", {"users": {
        "alice": {"age": 30, "city": "Berlin"},
        "bob": {"age": 25, "city": "Oslo"},
    }}),
    ("mixed list", {"items": [1, {"a": 1}, "text", [1, 2], None, True]}),
    ("quoting stress", {"notes": [
        "plain", "a,b", "a\nb", 'a"b', "a:b", "a\\b", "-x", "#tag", "42", "true",
        " x ", "a[b]{c}", "", "line1\r\nline2", "\t tabbed",
    ]}),
    ("unicode and emoji", {"message": "Hello \u4e16\u754c \U0001F44B", "tags": ["\U0001F389", "\U0001F38A"]}),
    ("empty containers", {"a": [], "b": {}, "c": [1, [], {}]}),
    ("deep nesting", {"root": {"level1": {"level2": {"level3": {"items": [
        {"id": 1, "val": "a"}, {"id": 2, "val": "b"},
    ]}}}}}),
    ("non-uniform array", {"items": [{"a": 1, "b": 2}, {"a": 1, "c": 3}]}),
    ("numbers", {"bignum": 9007199254740992, "decimal": 0.3333333333333333,
                 "neg": -42, "zero": 0, "negzero": -0.0, "small": 0.000001}),
]

def test_round_trip_against_reference():
    print("round-trip against @toon-format/toon reference decoder")
    node = _find_node()
    decode_cli = os.path.join(ROOT, "skill", "tests", "_toon_ref_decode.mjs")
    ref_available = node is not None and os.path.isfile(decode_cli)

    if not ref_available:
        check("reference decoder available", False,
              "node=%r decode_cli_exists=%s -- skipping round-trip checks; install the "
              "@toon-format/toon devDependency (npm install) and ensure node is on PATH "
              "to run them" % (node, os.path.isfile(decode_cli)))
        return

    # sanity: confirm the reference package is actually resolvable from decode_cli's cwd
    probe = subprocess.run([node, decode_cli], input="a: 1", capture_output=True, text=True,
                            cwd=os.path.dirname(decode_cli))
    if probe.returncode != 0:
        check("reference decoder resolvable", False,
              "run 'npm install' at the repo root to install the @toon-format/toon "
              "devDependency used for round-trip testing\n" + probe.stderr[-400:])
        return
    check("reference decoder resolvable", True)

    for name, value in ROUND_TRIP_CASES:
        encoded = toon.encode(value)
        decoded, err = _reference_decode(node, decode_cli, encoded)
        if err:
            check("round-trip: %s" % name, False, "decode error: %s\n---\n%s" % (err, encoded))
            continue
        check("round-trip: %s" % name, _json_equal(decoded, value),
              "encoded=%r\ndecoded=%r\noriginal=%r" % (encoded, decoded, value))

    # also round-trip the real sentinel xray.json sample end-to-end
    sample_path = os.path.join(ROOT, "tests", "samples", "xray_sentinel_sdk", "xray.json")
    if os.path.isfile(sample_path):
        with open(sample_path, "r", encoding="utf-8") as f:
            sample = json.load(f)
        encoded = toon.encode(sample)
        decoded, err = _reference_decode(node, decode_cli, encoded)
        check("round-trip: xray_sentinel_sdk/xray.json", err is None and _json_equal(decoded, sample),
              err or "structural mismatch (see diff manually; both are large)")
    else:
        check("xray_sentinel_sdk/xray.json present", False, sample_path)


def main():
    test_inline_form()
    test_list_form()
    test_tabular_form()
    test_keyed_tabular_form()
    test_quoting_edge_cases()
    test_nonuniform_falls_back_to_list()
    test_number_formatting()
    test_empty_object_and_root()
    test_round_trip_against_reference()
    print("")
    print("passed %d, failed %d" % (len(PASS), len(FAIL)))
    for name, detail in FAIL:
        print("  FAILED: %s %s" % (name, detail))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
