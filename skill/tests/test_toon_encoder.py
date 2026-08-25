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
    passing.
  - The same round trip through this module's own decode(), and a *cross
    check* that our decoder and the reference decoder produce the same value
    from the same document. That cross check is what makes the decoder
    trustworthy: "our encoder round-trips through our decoder" would also be
    satisfied by two matching misreadings of the spec, and xq answers every
    question out of decoded data, so a single misparsed row would quietly
    change answers with nothing left to notice it by.
  - Corrupt documents: a count that disagrees with its header, a bad indent
    and an unterminated quote each have to fail loudly.
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


# ---------------------------------------------------------------------------
# decode(): round trip through our own decoder, and cross-check against the
# reference decoder on the same documents
# ---------------------------------------------------------------------------

def _sample_xray():
    path = os.path.join(ROOT, "tests", "samples", "xray_sentinel_sdk", "xray.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_decode_round_trip():
    """decode(encode(v)) == v for every fixture above, and for the real sample.

    Pure Python, no Node: this is the check that must hold on any machine, since
    xq reads xray.toon through this decoder whether or not a reference
    implementation is installed.
    """
    print("decode round-trip (pure Python)")
    for name, value in ROUND_TRIP_CASES:
        encoded = toon.encode(value)
        try:
            decoded = toon.decode(encoded)
        except Exception as exc:  # noqa: BLE001 -- any failure is a test failure
            check("decode round-trip: %s" % name, False,
                  "%s: %s\n---\n%s" % (type(exc).__name__, exc, encoded))
            continue
        check("decode round-trip: %s" % name, _json_equal(decoded, value),
              "encoded=%r\ndecoded=%r\noriginal=%r" % (encoded, decoded, value))

    # Every literal-form assertion earlier in this file is also a round-trip
    # case: those pin the exact text, these pin that the text reads back.
    for name, value in (
        ("inline primitive array", {"tags": ["admin", "ops", "dev"]}),
        ("empty array field", {"tags": []}),
        ("root empty array", []),
        ("root primitive array", [1, 2, 3]),
        ("root empty object", {}),
        ("root primitive string", "hello"),
        ("root primitive number", 42),
        ("empty object field", {"obj": {}}),
        ("array of primitive arrays", {"pairs": [[1, 2], [3, 4]]}),
        ("single-entry object stays nested", {"users": {"alice": {"age": 30, "city": "Berlin"}}}),
        ("empty object disqualifies tabular", {"items": [{}, {"a": 1}]}),
        ("mixed-type column", {"items": [{"a": 1}, {"a": {"x": 1}}]}),
        ("tabular cell needing quotes", {"items": [{"a": "x,y"}, {"a": "p,q"}]}),
        ("quoted key", {"my-key": 1}),
        ("control char", {"note": "a\x01b"}),
        ("nested array in list item", {"items": [[{"a": 1}, {"a": 2}]]}),
        ("tabular first field in list item", {"items": [{"k": [{"a": 1}, {"a": 2}], "z": 9}]}),
        ("keyed tabular first field in list item",
         {"items": [{"m": {"a": {"x": 1}, "b": {"x": 2}}, "z": 1}]}),
        ("deeply nested list forms", {"x": [[[{"a": 1}, {"a": 2}]]]}),
    ):
        encoded = toon.encode(value)
        try:
            decoded = toon.decode(encoded)
        except Exception as exc:  # noqa: BLE001
            check("decode round-trip: %s" % name, False,
                  "%s: %s\n---\n%s" % (type(exc).__name__, exc, encoded))
            continue
        check("decode round-trip: %s" % name, _json_equal(decoded, value),
              "encoded=%r\ndecoded=%r\noriginal=%r" % (encoded, decoded, value))

    sample = _sample_xray()
    if sample is None:
        check("xray_sentinel_sdk/xray.json present for decode round-trip", False, "")
        return
    encoded = toon.encode(sample)
    decoded = toon.decode(encoded)
    check("decode round-trip: xray_sentinel_sdk/xray.json",
          _json_equal(decoded, sample), "structural mismatch (both are large)")

    # and the xray.toon actually sitting in the sample directory, which is what
    # xq reads -- not just one we re-encoded here
    on_disk = os.path.join(ROOT, "tests", "samples", "xray_sentinel_sdk", "xray.toon")
    if os.path.isfile(on_disk):
        with open(on_disk, "r", encoding="utf-8") as fh:
            text = fh.read()
        check("decode: the sample's own xray.toon equals its xray.json",
              _json_equal(toon.decode(text), sample), "structural mismatch")
    else:
        check("xray_sentinel_sdk/xray.toon present", False, on_disk)


def test_decode_cross_checked_against_reference():
    """Our decoder and the reference decoder must agree on the same documents.

    The encoder was verified by decoding its output with the reference. The
    decoder has no such external oracle of its own, so this is the substitute:
    feed one document to both decoders and require the same value. A bug that
    round-trips (encode and decode wrong in mirror-image ways) survives the test
    above and dies here.

    Key *order* is compared loosely against the reference on purpose: JavaScript
    objects place integer-like keys ("42") first regardless of insertion order,
    so the reference reorders keys our decoder preserves. Order is pinned
    exactly against the original value in test_decode_round_trip instead.
    """
    print("decode cross-checked against the reference decoder")
    node = _find_node()
    decode_cli = os.path.join(ROOT, "skill", "tests", "_toon_ref_decode.mjs")
    if node is None or not os.path.isfile(decode_cli):
        check("reference decoder available for cross-check", False,
              "node=%r decode_cli_exists=%s -- install the @toon-format/toon "
              "devDependency (npm install) and put node on PATH to run the "
              "cross-check" % (node, os.path.isfile(decode_cli)))
        return
    probe = subprocess.run([node, decode_cli], input="a: 1", capture_output=True,
                           text=True, cwd=os.path.dirname(decode_cli))
    if probe.returncode != 0:
        check("reference decoder resolvable for cross-check", False,
              "run 'npm install' at the repo root\n" + probe.stderr[-400:])
        return

    cases = list(ROUND_TRIP_CASES)
    sample = _sample_xray()
    if sample is not None:
        cases.append(("xray_sentinel_sdk/xray.json", sample))

    for name, value in cases:
        encoded = toon.encode(value)
        theirs, err = _reference_decode(node, decode_cli, encoded)
        if err:
            check("cross-check: %s" % name, False, "reference decode failed: %s" % err)
            continue
        try:
            ours = toon.decode(encoded)
        except Exception as exc:  # noqa: BLE001
            check("cross-check: %s" % name, False,
                  "our decoder failed where the reference succeeded: %s: %s"
                  % (type(exc).__name__, exc))
            continue
        check("cross-check: %s" % name, _json_equal_unordered(ours, theirs),
              "ours=%r\ntheirs=%r" % (ours, theirs))


def _json_equal_unordered(a, b):
    """_json_equal, but object key order is not compared (see the cross-check docstring)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_json_equal_unordered(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_json_equal_unordered(x, y) for x, y in zip(a, b))
    return a == b


# A declared count that disagrees with the rows under it, a broken indent or an
# unterminated quote all mean the document was altered after it was written.
# Reading it anyway would put a short table -- or a row's fields shifted by one
# -- into an xq answer, where nothing downstream can tell it apart from the
# truth. Each of these must raise.
CORRUPT_CASES = [
    ("tabular rows fewer than declared", "users[3]{id,name}:\n  1,a\n  2,b"),
    ("tabular rows more than declared", "users[2]{id,name}:\n  1,a\n  2,b\n  3,c"),
    ("tabular row has an extra cell", "users[2]{id,name}:\n  1,a\n  2,b,c"),
    ("tabular row is missing a cell", "users[2]{id,name}:\n  1,a\n  2"),
    ("inline array count disagrees", "tags[3]: a,b"),
    ("list items fewer than declared", "items[3]:\n  - 1\n  - 2"),
    ("list items more than declared", "items[2]:\n  - 1\n  - 2\n  - 3"),
    ("keyed entries disagree", "users[3:]{age}:\n  alice: 1\n  bob: 2"),
    ("keyed entry cell count disagrees", "users[2:]{age,city}:\n  a: 1\n  b: 2,x"),
    ("indent is not a multiple of indentSize", "a:\n   b: 1"),
    ("indent jumps two levels", "a:\n    b: 1"),
    ("tab used for indentation", "a:\n\tb: 1"),
    ("over-indented sibling field", "a:\n  b: 1\n    c: 2"),
    ("blank line inside a table", "users[2]{id}:\n  1\n\n  2"),
    ("unterminated quoted value", 'note: "abc'),
    ("unterminated quoted key", '"abc: 1'),
    ("unterminated quote in a row", 'users[1]{a}:\n  "x'),
    ("unknown escape sequence", 'note: "a\\qb"'),
    ("lone surrogate escape", 'note: "\\ud800"'),
    ("array length with a leading zero", "a[01]: 1"),
    ("negative array length", "a[-1]: 1"),
    ("keyed header without a field list", "a[2:]:\n  x: 1"),
    ("duplicate sibling key", "a: 1\na: 2"),
    ("duplicate field name", "u[1]{a,a}:\n  1,2"),
    ("content after the document root", "a: 1\n[2]: 1,2"),
    ("keyless header below the root", "a:\n  [2]: 1,2"),
]


def test_decode_rejects_corrupt_documents():
    print("decode rejects corrupt documents")
    for name, text in CORRUPT_CASES:
        try:
            got = toon.decode(text)
        except toon.ToonDecodeError as exc:
            # The line number is the part that makes the failure actionable: it
            # says which row of a 3000-line artifact stopped being readable.
            check("rejects %s" % name, exc.line is not None,
                  "raised without a line number: %s" % exc)
            continue
        except Exception as exc:  # noqa: BLE001
            check("rejects %s" % name, False,
                  "raised %s instead of ToonDecodeError: %s" % (type(exc).__name__, exc))
            continue
        check("rejects %s" % name, False, "accepted it and returned %r" % (got,))

    # The forms this module does not implement have to say so rather than
    # guessing: a tab-delimited document decoded as if it were comma-delimited
    # would return one string where a row of values was meant.
    for name, text in (("tab delimiter", "a[2\t]: 1\t2"),
                       ("pipe delimiter", "a[2|]: 1|2")):
        try:
            got = toon.decode(text)
        except NotImplementedError as exc:
            check("refuses the %s and names it" % name,
                  "delimiter" in str(exc), str(exc))
            continue
        except Exception as exc:  # noqa: BLE001
            check("refuses the %s and names it" % name, False,
                  "raised %s: %s" % (type(exc).__name__, exc))
            continue
        check("refuses the %s and names it" % name, False,
              "accepted it and returned %r" % (got,))

    # A trailing newline is what a file on disk has; it is not corruption.
    check("accepts a trailing newline",
          toon.decode("a: 1\n") == {"a": 1}, toon.decode("a: 1\n"))
    check("accepts a comment line",
          toon.decode("# a note\na: 1") == {"a": 1}, toon.decode("# a note\na: 1"))
    check("empty document is the empty object", toon.decode("") == {}, "")


def test_decode_number_and_string_discrimination():
    """A bare token is a number only in canonical S2 form; everything else is text.

    This is the inverse of the encoder's quoting rule, and the place where a
    decoder most easily changes data without failing: read "0042" as 42 and a
    zero-padded id silently becomes an integer, while reading 42 as "42" would
    turn every line number into a string.
    """
    print("bare token: number or string (SPEC S2, S7.2)")
    check_eq("integer stays an int", toon.decode("n: 42"), {"n": 42})
    check_eq("negative integer", toon.decode("n: -42"), {"n": -42})
    check_eq("decimal is a float", toon.decode("n: 1.5"), {"n": 1.5})
    check_eq("exponent form", toon.decode("n: 1e+21"), {"n": 1e21})
    check_eq("integer-valued float token stays an int",
             toon.decode("n: 2"), {"n": 2})
    check("integer token is an int, not a float",
          isinstance(toon.decode("n: 2")["n"], int), toon.decode("n: 2"))
    # Quoted: always a string, however number-like it looks.
    check_eq("quoted number is a string", toon.decode('n: "42"'), {"n": "42"})
    check_eq("quoted bool is a string", toon.decode('n: "true"'), {"n": "true"})
    check_eq("quoted null is a string", toon.decode('n: "null"'), {"n": "null"})
    # Bare but not canonical: a string, matching the reference. The encoder
    # quotes these anyway (its _NUMERIC_LIKE_RE is wider), so this only matters
    # for documents it did not write.
    check_eq("leading zeros are not a number", toon.decode("n: 007"), {"n": "007"})
    check_eq("leading plus is not a number", toon.decode("n: +5"), {"n": "+5"})
    check_eq("bare word is a string", toon.decode("n: admin"), {"n": "admin"})
    check_eq("literals", toon.decode("a: true\nb: false\nc: null"),
             {"a": True, "b": False, "c": None})
    check("bool is a bool, not 1", toon.decode("a: true")["a"] is True, "")


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
    test_decode_round_trip()
    test_decode_cross_checked_against_reference()
    test_decode_rejects_corrupt_documents()
    test_decode_number_and_string_discrimination()
    print("")
    print("passed %d, failed %d" % (len(PASS), len(FAIL)))
    for name, detail in FAIL:
        print("  FAILED: %s %s" % (name, detail))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
